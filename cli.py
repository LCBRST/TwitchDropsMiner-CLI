"""
CLI manager — drop-in replacement for `gui.GUIManager` plus an interactive
command shell.

Engine code (`twitch.py`, `channel.py`, `inventory.py`, `websocket.py`) only
ever touches a small surface of `Twitch.gui`:

    tray.change_icon / tray.notify
    status.update
    progress.stop_timer / progress.minute_almost_done / progress.display
    channels.{set_watching, clear_watching, clear, display, remove,
              get_selection, clear_selection}
    inv.{clear, add_campaign, update_drop}
    websockets.{update, remove}
    login (LoginForm protocol: ask_login / ask_enter_code / update)
    set_games / display_drop / clear_drop
    print / save / start / stop / close / close_window / prevent_close
    grab_attention / coro_unless_closed / wait_until_closed / running
    close_requested

`CLIManager` mimics that surface, prints sensible feedback to stdout, keeps
a small in-memory model of the relevant state, and also drives an interactive
shell that dispatches user commands to `commands.CommandRegistry`.
"""

from __future__ import annotations

import sys
import asyncio
import logging
from collections import abc
from datetime import datetime
from typing import Any, NoReturn, TypeVar, TYPE_CHECKING

from yarl import URL

from exceptions import ExitRequest
from translate import _
from constants import OUTPUT_FORMATTER

if TYPE_CHECKING:
    from twitch import Twitch
    from inventory import DropsCampaign, TimedDrop
    from channel import Channel
    from utils import Game


logger = logging.getLogger("TwitchDrops")

_T = TypeVar("_T")


# ---------------------------------------------------------------------------
# Sub-component stubs
# ---------------------------------------------------------------------------

class _CLITray:
    def __init__(self, cli: CLIManager) -> None:
        self._cli = cli
        self.state: str = "idle"

    def change_icon(self, state: str) -> None:
        self.state = state

    def notify(self, text: str, title: str | None = None) -> None:
        prefix = f"[{title}] " if title else ""
        self._cli.print(f"{prefix}{text}")

    # GUI-only no-ops
    def update_title(self, drop: TimedDrop | None) -> None:
        pass

    def stop(self) -> None:
        pass

    def minimize(self) -> None:
        pass

    def restore(self) -> None:
        pass


class _CLIStatus:
    def __init__(self, cli: CLIManager) -> None:
        self._cli = cli
        self.text: str = "idle"

    def update(self, text: str) -> None:
        self.text = text
        self._cli.print(f"[status] {text}")

    def clear(self) -> None:
        self.text = ""


class _CLIProgress:
    def __init__(self, cli: CLIManager) -> None:
        self._cli = cli
        self.current: TimedDrop | None = None

    def stop_timer(self) -> None:
        pass

    def start_timer(self) -> None:
        pass

    def minute_almost_done(self) -> bool:
        # The engine has a GQL fallback path that handles this gracefully.
        # Returning False is conservative; the real GUI tracks per-second
        # ticks which we don't have in CLI mode.
        return False

    def display(
        self,
        drop: TimedDrop | None,
        *,
        countdown: bool = True,
        subone: bool = False,
    ) -> None:
        prev = self.current
        self.current = drop
        if drop is None:
            if prev is not None:
                self._cli.print("[drop] cleared")
            return
        # Avoid spamming when the same drop just gets a per-minute tick
        if prev is None or prev.id != drop.id:
            self._cli.print(
                f"[drop] {drop.name} — {drop.current_minutes}/{drop.required_minutes}m"
            )


class _CLIChannels:
    def __init__(self, cli: CLIManager) -> None:
        self._cli = cli
        self._channels: dict[int, Channel] = {}
        self._watching: Channel | None = None
        self._selection: Channel | None = None

    def set_watching(self, channel: Channel) -> None:
        self._watching = channel
        game = channel.game.name if channel.game else "?"
        self._cli.print(f"[watch] {channel.name} ({game})")

    def clear_watching(self) -> None:
        if self._watching is not None:
            self._cli.print(f"[watch] cleared (was {self._watching.name})")
        self._watching = None

    def clear(self) -> None:
        self._channels.clear()
        self._selection = None

    def display(self, channel: Channel, *, add: bool = False) -> None:
        if add:
            self._channels[channel.id] = channel

    def remove(self, channel: Channel) -> None:
        self._channels.pop(channel.id, None)

    def get_selection(self) -> Channel | None:
        sel = self._selection
        self._selection = None  # selection consumed by the engine
        return sel

    def clear_selection(self) -> None:
        self._selection = None

    # CLI-only API used by the `watch` command
    def request(self, channel: Channel) -> None:
        self._selection = channel


class _CLIInventory:
    def __init__(self, cli: CLIManager) -> None:
        self._cli = cli
        self._campaigns: list[DropsCampaign] = []

    def clear(self) -> None:
        self._campaigns.clear()

    async def add_campaign(self, campaign: DropsCampaign) -> None:
        self._campaigns.append(campaign)

    def update_drop(self, drop: TimedDrop) -> None:
        # No-op — drops carry their own state which we read on demand.
        pass

    @property
    def campaigns(self) -> list[DropsCampaign]:
        return list(self._campaigns)


class _WSEntry:
    def __init__(self, idx: int) -> None:
        self.idx = idx
        self.status: str = "?"
        self.topics: int = 0


class _CLIWebsockets:
    def __init__(self, cli: CLIManager) -> None:
        self._cli = cli
        self._entries: dict[int, _WSEntry] = {}

    def update(
        self,
        idx: int,
        status: str | None = None,
        topics: int | None = None,
    ) -> None:
        entry = self._entries.setdefault(idx, _WSEntry(idx))
        changed = False
        if status is not None and status != entry.status:
            entry.status = status
            changed = True
        if topics is not None:
            entry.topics = topics
        if changed:
            self._cli.print(f"[ws#{idx}] {entry.status}")

    def remove(self, idx: int) -> None:
        if idx in self._entries:
            del self._entries[idx]
            self._cli.print(f"[ws#{idx}] removed")

    @property
    def entries(self) -> list[_WSEntry]:
        return [self._entries[i] for i in sorted(self._entries)]


class _CLISettingsStub:
    """Minimal stub for `gui.settings`. CLI exposes settings via commands."""

    def __init__(self, cli: CLIManager) -> None:
        self._cli = cli

    def set_games(self, games: set[Game]) -> None:
        pass

    def update_excluded_choices(self) -> None:
        pass

    def update_priority_choices(self) -> None:
        pass

    def clear_selection(self) -> None:
        pass


# ---------------------------------------------------------------------------
# Login handler — Device Code flow
# ---------------------------------------------------------------------------

class LoginData:
    def __init__(self, username: str = "", password: str = "", token: str = "") -> None:
        self.username = username
        self.password = password
        self.token = token


class CLILoginHandler:
    """Mirrors the public surface of `gui.LoginForm` used by `twitch.py`."""

    def __init__(self, cli: CLIManager) -> None:
        self._cli = cli
        self._user_id: int | None = None
        self._status: str = ""

    def update(self, status: str, user_id: int | None) -> None:
        self._status = status
        self._user_id = user_id
        self._cli.print(f"[login] {status}" + (f" (id={user_id})" if user_id else ""))

    @property
    def user_id(self) -> int | None:
        return self._user_id

    @property
    def status(self) -> str:
        return self._status

    async def ask_login(self) -> LoginData:
        # Username/password login is not supported in CLI mode — the Device
        # Code flow is selected instead. Returning an empty `LoginData` makes
        # the `_login` path in `twitch.py` short-circuit if it ever runs;
        # in practice the engine prefers `_oauth_login` (device flow).
        return LoginData()

    async def ask_enter_code(self, page_url: URL, user_code: str) -> None:
        self._cli.print("=" * 60)
        self._cli.print("Twitch login required (Device Code flow)")
        self._cli.print(f"  1. Open: {page_url}")
        self._cli.print(f"  2. Enter the code: {user_code}")
        self._cli.print("  3. Approve the login in your browser, then come back.")
        self._cli.print("=" * 60)
        # Best-effort browser open — silently ignore on headless boxes.
        try:
            import webbrowser
            webbrowser.open_new_tab(str(page_url))
        except Exception:
            pass

    async def wait_for_login_press(self) -> None:
        # The device-code path doesn't gate on a button press.
        return None


# ---------------------------------------------------------------------------
# Logging handler
# ---------------------------------------------------------------------------

class _CLIOutputHandler(logging.Handler):
    def __init__(self, cli: CLIManager) -> None:
        super().__init__()
        self._cli = cli

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._cli.print(self.format(record))
        except Exception:
            self.handleError(record)


# ---------------------------------------------------------------------------
# CLIManager
# ---------------------------------------------------------------------------

class CLIManager:
    def __init__(self, twitch: Twitch) -> None:
        self._twitch: Twitch = twitch
        self._poll_task: asyncio.Task[NoReturn] | None = None
        self._shell_task: asyncio.Task[None] | None = None
        self._close_requested = asyncio.Event()
        self._output_lines: list[str] = []
        self._max_output_lines = 500
        self._is_tty = sys.stdout.isatty()

        # Sub-components
        self.tray = _CLITray(self)
        self.status = _CLIStatus(self)
        self.progress = _CLIProgress(self)
        self.channels = _CLIChannels(self)
        self.inv = _CLIInventory(self)
        self.websockets = _CLIWebsockets(self)
        self.login = CLILoginHandler(self)
        self.settings = _CLISettingsStub(self)

        # Logging handler
        self._handler = _CLIOutputHandler(self)
        self._handler.setFormatter(OUTPUT_FORMATTER)
        logging.getLogger("TwitchDrops").addHandler(self._handler)

        # Banner
        from version import __version__
        self.print("=" * 60)
        self.print(f"  TwitchDropsMiner v{__version__} (CLI)")
        self.print("=" * 60)

    # ----- engine surface --------------------------------------------------

    @property
    def running(self) -> bool:
        return self._poll_task is not None

    @property
    def close_requested(self) -> bool:
        return self._close_requested.is_set()

    def prevent_close(self) -> None:
        self._close_requested.clear()

    async def wait_until_closed(self) -> None:
        await self._close_requested.wait()

    async def coro_unless_closed(self, coro: abc.Awaitable[_T]) -> _T:
        coro_task = asyncio.ensure_future(coro)
        close_task = asyncio.ensure_future(self._close_requested.wait())
        try:
            await asyncio.wait(
                {coro_task, close_task}, return_when=asyncio.FIRST_COMPLETED
            )
        except BaseException:
            coro_task.cancel()
            close_task.cancel()
            raise
        if close_task.done() and not coro_task.done():
            coro_task.cancel()
            raise ExitRequest()
        close_task.cancel()
        return coro_task.result()

    def start(self) -> None:
        if self._poll_task is None:
            self._poll_task = asyncio.create_task(self._poll(), name="cli-poll")
        if self._shell_task is None and self._twitch.settings.shell_enabled:
            self._shell_task = asyncio.create_task(
                self._shell_loop(), name="cli-shell"
            )

    def stop(self) -> None:
        if self._shell_task is not None:
            self._shell_task.cancel()
            self._shell_task = None
        if self._poll_task is not None:
            self._poll_task.cancel()
            self._poll_task = None

    async def _poll(self) -> NoReturn:
        # Heartbeat-only — keeps the manager "running" semantically.
        try:
            while True:
                await asyncio.sleep(1.0)
        except asyncio.CancelledError:
            raise

    def close(self, *args: Any) -> int:
        self._close_requested.set()
        try:
            self._twitch.close()
        except Exception:
            pass
        return 0

    def close_window(self) -> None:
        logging.getLogger("TwitchDrops").removeHandler(self._handler)

    def save(self, *, force: bool = False) -> None:
        # The image cache is GUI-only. Settings are saved via Twitch.save().
        pass

    def grab_attention(self, *, sound: bool = True) -> None:
        if sound:
            try:
                sys.stdout.write("\a")
                sys.stdout.flush()
            except Exception:
                pass

    def print(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        self._output_lines.append(line)
        if len(self._output_lines) > self._max_output_lines:
            del self._output_lines[: -self._max_output_lines]
        try:
            if self._is_tty:
                sys.stdout.write("\r\x1b[2K" + line + "\n")
            else:
                sys.stdout.write(line + "\n")
            sys.stdout.flush()
        except Exception:
            pass
        self._redraw_prompt()

    def set_games(self, games: set[Game]) -> None:
        self.settings.set_games(games)

    def display_drop(
        self,
        drop: TimedDrop,
        *,
        countdown: bool = True,
        subone: bool = False,
    ) -> None:
        self.progress.display(drop, countdown=countdown, subone=subone)
        self.tray.update_title(drop)

    def clear_drop(self) -> None:
        self.progress.display(None)
        self.tray.update_title(None)

    # ----- output buffer ---------------------------------------------------

    @property
    def output_buffer(self) -> list[str]:
        return list(self._output_lines)

    # ----- interactive shell ----------------------------------------------

    def _prompt_text(self) -> str:
        return f"tdm[{self.tray.state}]> "

    def _redraw_prompt(self) -> None:
        if self._shell_task is None or not self._is_tty:
            return
        try:
            sys.stdout.write(self._prompt_text())
            sys.stdout.flush()
        except Exception:
            pass

    async def _shell_loop(self) -> None:
        from commands import CommandRegistry
        self._registry = CommandRegistry(self._twitch, self)
        loop = asyncio.get_running_loop()
        # Print initial prompt
        self._redraw_prompt()
        while not self._close_requested.is_set():
            try:
                line = await loop.run_in_executor(None, self._read_line)
            except (EOFError, KeyboardInterrupt):
                self.print("Got EOF on stdin — closing.")
                self.close()
                return
            except asyncio.CancelledError:
                raise
            if line is None:
                # stdin closed
                self.close()
                return
            line = line.strip()
            if not line:
                self._redraw_prompt()
                continue
            try:
                await self._registry.dispatch(line)
            except ExitRequest:
                self.close()
                return
            except Exception:
                logger.exception("error while running command")
            self._redraw_prompt()

    def _read_line(self) -> str | None:
        try:
            return input()
        except EOFError:
            return None
