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

import re
import sys
import asyncio
import logging
from collections import abc
from datetime import datetime
from pathlib import Path
from typing import Any, NoReturn, TypeVar, TYPE_CHECKING

from yarl import URL

from exceptions import ExitRequest
from translate import _
from constants import OUTPUT_FORMATTER, WORKING_DIR

# Use prompt_toolkit for a fullscreen TUI shell: scrollable log area,
# command history, line-editing, tab completion, and mouse-wheel support.
# The TUI only activates after login; before that print() writes to stdout.
# Falls back to GNU readline if prompt_toolkit isn't available.
try:
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.completion import Completer, Completion
    from prompt_toolkit.history import FileHistory
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import (
        Layout, HSplit, Window,
    )
    from prompt_toolkit.layout.controls import (
        BufferControl, FormattedTextControl,
    )
    from prompt_toolkit.layout.processors import BeforeInput
    from prompt_toolkit.styles import Style as _Style
    _HAS_PROMPT_TOOLKIT = True
except ImportError:
    _HAS_PROMPT_TOOLKIT = False
    try:
        import readline  # type: ignore[no-redef]
        _HAS_READLINE = True
    except ImportError:
        try:
            import gnureadline as readline  # type: ignore[no-redef]
            _HAS_READLINE = True
        except ImportError:
            readline = None  # type: ignore[assignment]
            _HAS_READLINE = False

_HISTORY_PATH = Path(WORKING_DIR, ".cli_history")
_HISTORY_LENGTH = 1000

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
        if title:
            self._cli.print(_("cli", "notify").format(title=title, text=text))
        else:
            self._cli.print(text)

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
    # Extract "(N/M)" progress counters so we can render a bar once
    # instead of flooding the log with near-identical lines.
    # Only prints when the counter reaches completion (cur >= total).
    _COUNTER_RE = re.compile(r"^(.*?)\s*\((\d+)/(\d+)\)$")

    def __init__(self, cli: CLIManager) -> None:
        self._cli = cli
        self.text: str = "idle"
        self._seen: set[str] = set()

    def update(self, text: str) -> None:
        self.text = text
        m = self._COUNTER_RE.match(text)
        if m:
            base = m.group(1).strip()
            cur, total = int(m.group(2)), int(m.group(3))
            if base not in self._seen and cur >= total and total > 0:
                self._seen.add(base)
                bar = self._cli._render_bar(1.0, 16)
                self._cli.print(
                    _("cli", "status_progress").format(
                        text=base, bar=bar, cur=cur, total=total,
                    )
                )
            return
        self._cli.print(_("cli", "status").format(text=text))

    def clear(self) -> None:
        self.text = ""
        self._seen.clear()


class _CLIProgress:
    def __init__(self, cli: CLIManager) -> None:
        self._cli = cli
        self.current: TimedDrop | None = None
        self._last_tick: float = 0.0   # last time a minute tick was observed
        self._gql_checked: float = 0.0  # last time the GQL fallback was checked

    def stop_timer(self) -> None:
        self._last_tick = 0.0

    def start_timer(self) -> None:
        from time import time
        self._last_tick = time()

    def minute_almost_done(self) -> bool:
        # In CLI mode there are no per-second GUI ticks, so approximate:
        # signal "minute almost done" when ~55 s have passed since the
        # last progress tick OR since the last GQL fallback check.  This
        # lets _watch_loop trigger the GQL / bump_minutes fallback paths
        # so drop progress keeps advancing even when the WebSocket
        # delivers few (or no) drop-progress events.
        if self.current is None:
            return False
        from time import time
        now = time()
        # Only fire at most once per ~55 s to avoid hammering GQL.
        if now - self._gql_checked < 55:
            return False
        if now - self._last_tick >= 55:
            self._gql_checked = now
            return True
        return False

    def display(
        self,
        drop: TimedDrop | None,
        *,
        countdown: bool = True,
        subone: bool = False,
    ) -> None:
        from time import time
        prev = self.current
        self.current = drop
        if drop is None:
            if prev is not None:
                self._cli.print(_("cli", "drop", "cleared"))
            return
        # Record a progress tick so minute_almost_done can fire correctly.
        # A subone pre-display isn't a real progress event, so skip it.
        if not subone:
            self._last_tick = time()
        # Avoid spamming when the same drop just gets a per-minute tick
        if prev is None or prev.id != drop.id:
            campaign = drop.campaign
            bar_w = 20
            c_bar = self._cli._render_bar(campaign.progress, bar_w)
            d_bar = self._cli._render_bar(drop.progress, bar_w)
            self._cli.print(
                _("cli", "drop", "active_full").format(
                    campaign=campaign.name,
                    game=campaign.game.name,
                    c_bar=c_bar,
                    c_pct=f"{campaign.progress:.0%}",
                    c_claimed=campaign.claimed_drops,
                    c_total=campaign.total_drops,
                    drop_name=drop.name,
                    rewards=drop.rewards_text(),
                    d_bar=d_bar,
                    d_pct=f"{drop.progress:.0%}",
                    current=drop.current_minutes,
                    required=drop.required_minutes,
                )
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
        self._cli.print(_("cli", "watch", "watching").format(channel=channel.name, game=game))

    def clear_watching(self) -> None:
        if self._watching is not None:
            self._cli.print(_("cli", "watch", "cleared").format(channel=self._watching.name))
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
            self._cli.print(_("cli", "ws", "status").format(idx=idx, status=entry.status))

    def remove(self, idx: int) -> None:
        if idx in self._entries:
            del self._entries[idx]
            self._cli.print(_("cli", "ws", "removed").format(idx=idx))

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
        if user_id is not None:
            self._cli.print(_("cli", "login", "status_id").format(status=status, id=user_id))
        else:
            self._cli.print(_("cli", "login", "status").format(status=status))

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
        self._cli.print(_("cli", "separator"))
        self._cli.print(_("cli", "login", "header"))
        self._cli.print(_("cli", "login", "step_open").format(url=page_url))
        self._cli.print(_("cli", "login", "step_code").format(code=user_code))
        self._cli.print(_("cli", "login", "step_approve"))
        self._cli.print(_("cli", "separator"))
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
# prompt_toolkit completer
# ---------------------------------------------------------------------------

if _HAS_PROMPT_TOOLKIT:

    class _CLICompleter(Completer):
        """Context-sensitive tab-completion: commands, args, game/channel names."""

        _SUBCOMMANDS: dict[str, list[str]] = {
            "priority": ["list", "add", "remove", "move", "clear"],
            "exclude": ["list", "add", "remove", "clear"],
        }
        _STATIC_ARGS: dict[str, list[str]] = {
            "mode": ["priority_only", "ending_soonest", "low_avbl_first"],
            "quality": ["0", "1", "2"],
            "level": ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
            "reload-interval": [],
        }
        _SETTING_KEYS: list[str] = [
            "proxy", "language", "exclude", "priority", "priority_mode",
            "connection_quality", "reload_interval", "tray_notifications",
            "dark_mode", "autostart_tray",
        ]

        def __init__(self, cli: "CLIManager") -> None:
            self._cli = cli

        def get_completions(self, document, complete_event):
            registry = getattr(self._cli, "_registry", None)
            if registry is None:
                return
            text = document.text_before_cursor.lstrip()
            tokens = text.split()
            word = document.get_word_before_cursor()
            word_lower = word.lower()

            if not tokens:
                return

            cmd = tokens[0].lower()

            # First word: complete command names (only when no trailing space)
            if len(tokens) == 1 and not text.endswith(" "):
                for c in registry.all():
                    if c.name.startswith(word_lower):
                        yield Completion(
                            c.name, start_position=-len(word),
                            display_meta=c.summary,
                        )
                return

            # Subcommand completion
            if cmd in self._SUBCOMMANDS and len(tokens) <= 2:
                for s in self._SUBCOMMANDS[cmd]:
                    if s.startswith(word_lower):
                        yield Completion(s, start_position=-len(word))
                return

            # Game name completion for priority/exclude add/remove
            if cmd in ("priority", "exclude") and len(tokens) >= 2:
                sub = tokens[1]
                if sub == "add":
                    games = self._collect_game_names()
                    for g in sorted(games, key=str.lower):
                        if g.lower().startswith(word_lower):
                            yield Completion(g, start_position=-len(word))
                elif sub == "remove":
                    src = (
                        list(self._cli._twitch.settings.priority) if cmd == "priority"
                        else sorted(self._cli._twitch.settings.exclude)
                    )
                    for g in src:
                        if g.lower().startswith(word_lower):
                            yield Completion(g, start_position=-len(word))
                return

            # Channel name completion for watch
            if cmd == "watch":
                for ch in self._cli.channels._channels.values():
                    if ch._login.lower().startswith(word_lower):
                        yield Completion(ch._login, start_position=-len(word),
                                         display_meta=ch.name)
                return

            # Static argument completion
            if cmd in self._STATIC_ARGS:
                for val in self._STATIC_ARGS[cmd]:
                    if val.lower().startswith(word_lower):
                        yield Completion(val, start_position=-len(word))
                return

            # Lang completion
            if cmd == "lang":
                from constants import LANG_PATH
                for f in sorted(LANG_PATH.glob("*.json")):
                    code = f.stem
                    if code.lower().startswith(word_lower):
                        yield Completion(code, start_position=-len(word))
                return

            # help: complete command names
            if cmd == "help":
                for c in registry.all():
                    if c.name.startswith(word_lower):
                        yield Completion(c.name, start_position=-len(word),
                                         display_meta=c.summary)
                return

            # set/get: complete setting keys
            if cmd in ("set", "get"):
                for k in self._SETTING_KEYS:
                    if k.startswith(word_lower):
                        yield Completion(k, start_position=-len(word))
                return

        def _collect_game_names(self) -> set[str]:
            """Collect known game names from inventory, channels, and settings."""
            names: set[str] = set()
            t = self._cli._twitch
            for camp in t.inventory:
                names.add(camp.game.name)
            for ch in self._cli.channels._channels.values():
                if ch.game is not None:
                    names.add(ch.game.name)
            for g in t.settings.priority:
                names.add(g)
            for g in t.settings.exclude:
                names.add(g)
            return names


# ---------------------------------------------------------------------------
# CLIManager
# ---------------------------------------------------------------------------

class CLIManager:
    def __init__(self, twitch: Twitch) -> None:
        self._twitch: Twitch = twitch
        self._poll_task: asyncio.Task[NoReturn] | None = None
        self._shell_task: asyncio.Task[None] | None = None
        self._close_requested = asyncio.Event()
        self._start_time = datetime.now()
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
        self.print(_("cli", "separator"))
        self.print(_("cli", "banner").format(version=__version__))
        self.print(_("cli", "separator"))

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

    def clear_screen(self) -> None:
        """Clear the log display area.

        When the prompt_toolkit TUI is active the log buffer is cleared;
        otherwise a best-effort ANSI escape is written to stdout.
        """
        app = getattr(self, "_app", None)
        buf: Buffer | None = getattr(self, "_log_buffer", None)
        if app is not None and buf is not None and app.is_running:
            buf.text = ""
            try:
                app.invalidate()
            except Exception:
                pass
        else:
            try:
                sys.stdout.write("\x1b[2J\x1b[H")
                sys.stdout.flush()
            except Exception:
                pass

    def print(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {message}"
        self._output_lines.append(line)
        if len(self._output_lines) > self._max_output_lines:
            del self._output_lines[: -self._max_output_lines]
        # When the TUI is running, feed the log buffer so output appears in
        # the scrollable log area.  Otherwise write to stdout directly.
        app = getattr(self, "_app", None)
        buf: Buffer | None = getattr(self, "_log_buffer", None)
        if app is not None and buf is not None and app.is_running:
            buf.text = buf.text + line + "\n"
            if getattr(self, "_log_follow", True):
                buf.cursor_position = len(buf.text)
            try:
                app.invalidate()
            except Exception:
                pass
        else:
            try:
                sys.stdout.write(line + "\n")
                sys.stdout.flush()
            except Exception:
                pass

    def print_raw(self, message: str) -> None:
        """Print without a timestamp — for informational / display output."""
        self._output_lines.append(message)
        if len(self._output_lines) > self._max_output_lines:
            del self._output_lines[: -self._max_output_lines]
        app = getattr(self, "_app", None)
        buf: Buffer | None = getattr(self, "_log_buffer", None)
        if app is not None and buf is not None and app.is_running:
            buf.text = buf.text + message + "\n"
            if getattr(self, "_log_follow", True):
                buf.cursor_position = len(buf.text)
            try:
                app.invalidate()
            except Exception:
                pass
        else:
            try:
                sys.stdout.write(message + "\n")
                sys.stdout.flush()
            except Exception:
                pass

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

    # ----- progress bar rendering ------------------------------------------

    @staticmethod
    def _render_bar(progress: float, width: int = 20) -> str:
        """Render an ASCII progress bar like '████████░░░░░░ 45%'."""
        if progress < 0:
            progress = 0.0
        elif progress > 1:
            progress = 1.0
        filled = int(progress * width)
        bar = "█" * filled + "░" * (width - filled)
        return f"{bar} {progress:.0%}"

    # ----- output buffer ---------------------------------------------------

    @property
    def output_buffer(self) -> list[str]:
        return list(self._output_lines)

    # ----- interactive shell ----------------------------------------------

    _PROMPT_STYLE = _Style.from_dict({
        "prompt": "#00ff00 bold",
        "state": "#00aaaa italic",
        "separator": "#888888",
        "status": "#666666",
        "topbar": "bg:#333333 #ffffff",
        "log": "",
        "input": "",
    }) if _HAS_PROMPT_TOOLKIT else None

    def _prompt_html(self):
        """Styled prompt — just a simple arrow."""
        return [
            ("class:prompt", "> "),
        ]

    def _top_bar_text(self) -> str:
        """Persistent top status bar: engine state, login, watching, counts, progress."""
        from version import __version__
        twitch = self._twitch
        raw_state = twitch._state.name if hasattr(twitch, "_state") else "?"
        watching = self.channels._watching
        # Map internal state to a user-visible label.
        # CHANNEL_SWITCH is the steady "watching" state — once a channel
        # is being watched, show WATCHING instead of the internal enum name.
        if raw_state == "CHANNEL_SWITCH" and watching is not None:
            state_name = "WATCHING"
        else:
            state_name = raw_state
        drop = self.progress.current
        ws_count = len(self.websockets.entries)

        # Line 1: core status
        uid = f"({self.login.user_id})" if self.login.user_id else ""
        now = datetime.now()
        secs = int((now - self._start_time).total_seconds())
        d, rest = divmod(secs, 86400)
        h, m, s = rest // 3600, rest % 3600 // 60, rest % 60
        uptime = f"Run: {d}:{h:02d}:{m:02d}:{s:02d}"
        parts = [
            f"Version: {__version__}",
            f"Engine: {state_name}",
            f"Login: {self.login.status}{uid}",
        ]
        if watching is not None:
            parts.append(f"Watch: {watching.name}")
        parts.append(f"Campaigns: {len(twitch.inventory)}/{len(twitch.wanted_games)}")
        parts.append(f"Ch: {len(twitch.channels)}")
        if ws_count:
            parts.append(f"WS: {ws_count}")
        parts.append(f"Sys: {now.strftime('%H:%M:%S')}")
        parts.append(uptime)
        line1 = " │ ".join(parts)

        # Line 2: drop progress (right-aligned)
        if drop is not None:
            campaign = drop.campaign
            bar_w = 14
            c_bar = self._render_bar(campaign.progress, bar_w)
            d_bar = self._render_bar(drop.progress, bar_w)
            line2 = (
                f"Campaign: {c_bar} ({campaign.claimed_drops}/{campaign.total_drops})  "
                f"Drop: {d_bar} ({drop.current_minutes}/{drop.required_minutes}m)"
            )
        else:
            line2 = ""
        return f"{line1}\n{line2}"

    _log_follow: bool = True  # auto-scroll to bottom on new output

    def _redraw_prompt(self) -> None:
        pass  # the TUI manages its own display

    # ---- prompt_toolkit TUI shell ------------------------------------------

    if _HAS_PROMPT_TOOLKIT:

        async def _shell_loop(self) -> None:
            from commands import CommandRegistry
            self._registry = CommandRegistry(self._twitch, self)

            # ---- buffers ---------------------------------------------------

            log_buffer = Buffer(multiline=True, read_only=False)
            input_buffer = Buffer(
                multiline=False,
                history=FileHistory(str(_HISTORY_PATH)),
                completer=_CLICompleter(self),
                complete_while_typing=False,
            )

            # Stash references.  print() won't write to log_buffer until
            # app.is_running is True (i.e. inside run_async), so all login
            # output still goes to stdout.
            self._log_buffer = log_buffer
            self._input_buffer = input_buffer
            self._log_follow = True

            # ---- key bindings ----------------------------------------------

            kb = KeyBindings()

            @kb.add("enter")
            def _submit(event):
                text = input_buffer.text
                input_buffer.reset()
                if text.strip():
                    # Manually feed the history — the custom key binding bypasses
                    # the Buffer's accept flow that would normally do this.
                    # Skip empty/whitespace input so they don't clutter history.
                    if input_buffer.history is not None:
                        input_buffer.history.append_string(text)
                    asyncio.ensure_future(self._dispatch_cmd(text))

            @kb.add("c-c")
            def _abort(event):
                self.close()
                event.app.exit()

            @kb.add("c-d")
            def _eof(event):
                if not input_buffer.text:
                    self.close()
                    event.app.exit()

            # Log view scrolling — pause auto-follow when browsing history.
            @kb.add("pageup")
            def _page_up(event):
                rows = event.app.output.get_size().rows
                log_buffer.cursor_up(max(rows - 2, 1))
                self._log_follow = False

            @kb.add("pagedown")
            def _page_down(event):
                rows = event.app.output.get_size().rows
                log_buffer.cursor_down(max(rows - 2, 1))
                if log_buffer.cursor_position >= len(log_buffer.text) - 1:
                    self._log_follow = True

            @kb.add("c-home")
            def _top(event):
                log_buffer.cursor_position = 0
                self._log_follow = False

            @kb.add("c-end")
            def _bottom(event):
                log_buffer.cursor_position = len(log_buffer.text)
                self._log_follow = True

            # ---- layout ----------------------------------------------------

            top_bar = Window(
                height=2,
                content=FormattedTextControl(
                    lambda: self._top_bar_text()
                ),
                style="class:topbar",
                align="RIGHT",
            )

            log_window = Window(
                content=BufferControl(
                    buffer=log_buffer,
                    focusable=False,
                ),
                wrap_lines=True,
                always_hide_cursor=True,
            )

            input_window = Window(
                height=1,
                content=BufferControl(
                    buffer=input_buffer,
                    input_processors=[BeforeInput(self._prompt_html)],
                ),
            )

            root = HSplit([
                top_bar,
                log_window,
                input_window,
            ])

            layout = Layout(root, focused_element=input_buffer)

            # ---- application -----------------------------------------------

            app = Application(
                layout=layout,
                key_bindings=kb,
                style=self._PROMPT_STYLE,
                full_screen=True,
                mouse_support=True,
            )
            self._app = app

            # Seed the log buffer with buffered pre-TUI output.
            if self._output_lines:
                log_buffer.text = "\n".join(self._output_lines) + "\n"

            # First-run guide: show when no priority games configured.
            if not self._twitch.settings.priority:
                log_buffer.text += (
                    "\n"
                    + _("cli", "commands", "welcome")
                    + "\n\n"
                )

            # Periodic refresh keeps the status-line progress bars
            # alive even when no other print activity is happening.
            async def _refresh_tui() -> NoReturn:
                while True:
                    await asyncio.sleep(1)
                    try:
                        app.invalidate()
                    except Exception:
                        pass

            _refresh_task = asyncio.create_task(_refresh_tui(), name="tui-refresh")
            try:
                await app.run_async()
            finally:
                _refresh_task.cancel()
                try:
                    await _refresh_task
                except asyncio.CancelledError:
                    pass
                # Trim the history file to _HISTORY_LENGTH lines.
                if _HISTORY_PATH.exists():
                    try:
                        lines = _HISTORY_PATH.read_text(encoding="utf-8").splitlines(True)
                        if len(lines) > _HISTORY_LENGTH:
                            _HISTORY_PATH.write_text(
                                "".join(lines[-_HISTORY_LENGTH:]), encoding="utf-8"
                            )
                    except OSError:
                        pass
                self._app = None
                self._log_follow = True

        async def _dispatch_cmd(self, line: str) -> None:
            """Handle a command entered in the TUI input line."""
            # Print a thin separator so consecutive commands
            # are visually distinct in the log.
            self.print("─" * 56)
            try:
                await self._registry.dispatch(line)
            except ExitRequest:
                app = getattr(self, "_app", None)
                if app is not None:
                    app.exit()
                self.close()
            except Exception:
                logger.exception("error while running command")

    # ---- readline fallback shell ------------------------------------------

    else:

        async def _shell_loop(self) -> None:  # type: ignore[no-redef]
            from commands import CommandRegistry
            self._registry = CommandRegistry(self._twitch, self)

            if _HAS_READLINE:
                try:
                    readline.read_history_file(str(_HISTORY_PATH))
                except (FileNotFoundError, OSError):
                    pass
                readline.set_history_length(_HISTORY_LENGTH)
                readline.parse_and_bind("tab: complete")
                readline.set_completer(self._completer)

            loop = asyncio.get_running_loop()
            self._redraw_prompt()
            while not self._close_requested.is_set():
                try:
                    raw_line = await loop.run_in_executor(None, self._read_line)
                except (EOFError, KeyboardInterrupt):
                    self.print(_("cli", "eof"))
                    self.close()
                    return
                except asyncio.CancelledError:
                    raise
                if raw_line is None:
                    self.close()
                    return
                raw_line = raw_line.strip()
                if not raw_line:
                    self._redraw_prompt()
                    continue
                try:
                    self.print("─" * 56)
                    await self._registry.dispatch(raw_line)
                except ExitRequest:
                    if _HAS_READLINE:
                        try:
                            readline.write_history_file(str(_HISTORY_PATH))
                        except OSError:
                            pass
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

        def _completer(self, text: str, state: int) -> str | None:
            """Tab-completion callback for readline: cycles through matching commands."""
            registry = getattr(self, "_registry", None)
            if registry is None:
                return None
            matches = [name for name in registry._commands if name.startswith(text.lower())]
            seen: set[str] = set()
            uniq: list[str] = []
            for m in sorted(matches):
                cmd = registry.find(m)
                if cmd is None:
                    continue
                if cmd.name not in seen:
                    seen.add(cmd.name)
                    uniq.append(cmd.name)
            return uniq[state] if state < len(uniq) else None
