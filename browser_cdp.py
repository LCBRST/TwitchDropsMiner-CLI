"""
A temporary Chromium this app owns, driven over the DevTools protocol.

Twitch's SDK issues the integrity proof from inside a real browser, so renewal
needs one; so does signing in, which is why the browser can also be started
with a window. Either way it is a throwaway profile of our own, never the
user's browser, and the profile and the listening socket are cleaned up with
it.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import re
import shutil
import signal
import sys
import tempfile
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Protocol

import aiohttp
from yarl import URL

from session_import import SessionImportError


logger = logging.getLogger("TwitchDrops")

# The maximum amount of data we are willing to have buffered for one reply.
MAX_MESSAGE_BYTES = 16 * 1024 * 1024

# The endpoints this module reasons about; see DevToolsConnection.
GQL_URL = "https://gql.twitch.tv/gql"
INTEGRITY_URL = "https://gql.twitch.tv/integrity"


def find_browser(explicit: str = "") -> str | None:
    """
    Locate a Chromium-based browser to drive.

    An explicit path wins; otherwise the usual names are tried, then the places
    each platform installs Chrome (and Edge, which is Chromium and is present on
    every Windows install as a last resort).
    """
    if explicit:
        path = Path(explicit)
        return str(path) if path.is_file() else None
    for name in ("chromium", "chromium-browser", "google-chrome", "google-chrome-stable"):
        found = shutil.which(name)
        if found:
            return found
    candidates: list[Path] = []
    if sys.platform == "win32":
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
            base = os.environ.get(variable)
            if not base:
                continue
            candidates.append(Path(base, "Google", "Chrome", "Application", "chrome.exe"))
        for variable in ("ProgramFiles", "ProgramFiles(x86)"):
            base = os.environ.get(variable)
            if not base:
                continue
            candidates.append(Path(base, "Microsoft", "Edge", "Application", "msedge.exe"))
    elif sys.platform == "darwin":
        candidates.append(Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
        candidates.append(Path("/Applications/Chromium.app/Contents/MacOS/Chromium"))
    else:
        candidates += [Path("/usr/bin/chromium"), Path("/usr/bin/google-chrome"),
                        Path("/snap/bin/chromium")]
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


class DevToolsConnection:
    """Multiplexes CDP command replies and the few network events we care about."""

    def __init__(
        self, socket_: Any, *, extra_events: frozenset[str] = frozenset(),
        drop_oldest: bool = False,
    ):
        self.socket = socket_
        self.extra_events = extra_events
        # An interactive session produces events far faster than a slow viewer
        # renders them, and a stale frame is worth nothing. Dropping the oldest
        # keeps that stream alive, where tearing the connection down once the
        # queue fills - the right answer for renewal, which must see everything
        # - would end the session the user is in the middle of.
        self.drop_oldest = drop_oldest
        self._sequence = 0
        self._pending: dict[int, asyncio.Future] = {}
        self.events: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=256)
        self._requests: set[str] = set()
        self._reader = asyncio.create_task(self._receive())

    def _offer(self, event: dict[str, Any]) -> bool:
        """Queue an event. False means the connection can no longer be trusted."""
        if self.events.full():
            if not self.drop_oldest:
                return False
            with suppress(asyncio.QueueEmpty):
                self.events.get_nowait()
        self.events.put_nowait(event)
        return True

    async def _receive(self) -> None:
        try:
            async for message in self.socket:
                if message.type != aiohttp.WSMsgType.TEXT:
                    break
                data = message.json()
                if not isinstance(data, dict):
                    break
                sequence = data.get("id")
                future = self._pending.get(sequence) if isinstance(sequence, int) else None
                if future is not None and not future.done():
                    if "error" in data:
                        future.set_exception(SessionImportError("BROWSER_PROTOCOL"))
                    else:
                        future.set_result(data.get("result", {}))
                    continue
                method, params = data.get("method"), data.get("params", {})
                if not isinstance(params, dict):
                    break
                # Extra events are not request-scoped and carry no requestId, so
                # they have to be queued before any of that is looked at.
                if method in self.extra_events:
                    if not self._offer(data):
                        break
                    continue
                request_id = params.get("requestId")
                if method == "Network.requestWillBeSent":
                    url = params.get("request", {}).get("url")
                    relevant = url in (GQL_URL, INTEGRITY_URL)
                elif method == "Network.responseReceived":
                    url = params.get("response", {}).get("url")
                    relevant = params.get("type") != "Preflight" and url in (GQL_URL, INTEGRITY_URL)
                elif method == "Network.loadingFinished":
                    relevant = request_id in self._requests
                else:
                    continue
                if not relevant:
                    continue
                if not isinstance(request_id, str):
                    break
                if method == "Network.loadingFinished":
                    self._requests.discard(request_id)
                else:
                    self._requests.add(request_id)
                if len(self._requests) > 256 or not self._offer(data):
                    break
        except (aiohttp.ClientError, ValueError, TypeError):
            pass
        finally:
            for future in self._pending.values():
                if not future.done():
                    future.set_exception(SessionImportError("BROWSER_PROTOCOL"))
            if self.events.full():
                self.events.get_nowait()
            self.events.put_nowait(None)

    async def command(self, method: str, params: dict[str, Any] | None = None, *, timeout: float = 30) -> Any:
        self._sequence += 1
        sequence = self._sequence
        future: asyncio.Future = asyncio.get_running_loop().create_future()
        self._pending[sequence] = future

        async def send_and_wait() -> Any:
            await self.socket.send_json({"id": sequence, "method": method, "params": params or {}})
            return await future

        try:
            # The send is inside the timeout too, deliberately. A browser that
            # has stopped reading its own debugging socket fills the write
            # buffer, and sending then blocks forever - a command that never
            # returns is far worse than one that fails, because there is nothing
            # to report and nothing to retry.
            return await asyncio.wait_for(send_and_wait(), timeout)
        finally:
            self._pending.pop(sequence, None)

    async def body(self, request_id: str) -> Any:
        body = await self.command("Network.getResponseBody", {"requestId": request_id})
        raw = base64.b64decode(body["body"]) if body.get("base64Encoded") else body["body"]
        return json.loads(raw)

    async def close(self) -> None:
        self._reader.cancel()
        await asyncio.gather(self._reader, return_exceptions=True)


def local_endpoint(address: str, value: str, *, target_id: str | None = None) -> URL:
    """
    Validate a DevTools websocket URL before dialling it.

    Every URL here arrives from the browser we started, but a malformed one is
    still worth refusing outright rather than connecting somewhere else.
    """
    try:
        endpoint = URL(value)
        if (
            endpoint.scheme != "ws"
            or endpoint.host not in ("127.0.0.1", "localhost", "::1")
            or endpoint.port != URL(address).port
            or endpoint.user is not None
            or endpoint.password is not None
            or endpoint.query
            or endpoint.fragment
            or (
                endpoint.raw_path != f"/devtools/page/{target_id}"
                if target_id is not None
                else not re.fullmatch(r"/devtools/browser/[a-zA-Z0-9-]+", endpoint.raw_path)
            )
        ):
            raise ValueError
    except (ValueError, TypeError):
        raise SessionImportError("BROWSER_PROTOCOL") from None
    return endpoint


@asynccontextmanager
async def browser_target(
    address: str, *, extra_events: frozenset[str] = frozenset(),
    drop_oldest: bool = False,
) -> AsyncIterator[DevToolsConnection]:
    """Open a page target, hand it over, and close only that target."""
    target_id = None
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=30)) as http:
        try:
            async with http.put(address + "/json/new?about:blank", allow_redirects=False) as response:
                if response.status != 200:
                    raise SessionImportError("BROWSER_PROTOCOL")
                target = await response.json()
            if not re.fullmatch(r"[a-zA-Z0-9-]+", target["id"]):
                raise SessionImportError("BROWSER_PROTOCOL")
            target_id = target["id"]
            endpoint = local_endpoint(address, target["webSocketDebuggerUrl"], target_id=target_id)
            async with http.ws_connect(
                endpoint, max_msg_size=MAX_MESSAGE_BYTES,
                timeout=aiohttp.ClientWSTimeout(ws_close=2),
            ) as socket_:
                protocol = DevToolsConnection(
                    socket_, extra_events=extra_events, drop_oldest=drop_oldest
                )
                try:
                    yield protocol
                finally:
                    await protocol.close()
        except (aiohttp.ClientError, ValueError, KeyError, TypeError):
            raise SessionImportError("BROWSER_PROTOCOL") from None
        finally:
            if target_id is not None:
                with suppress(aiohttp.ClientError, TimeoutError):
                    async with http.get(
                        address + "/json/close/" + target_id, allow_redirects=False,
                        timeout=aiohttp.ClientTimeout(total=2),
                    ) as response:
                        await response.read()


class OwnedChromium:
    """Own a temporary profile and process group; never attach to a user's browser."""

    def __init__(
        self, executable: str, *, no_sandbox: bool = False, startup_timeout: float = 20,
        headless: bool = True, extra_args: Sequence[str] = (),
        env: Mapping[str, str] | None = None, profile_prefix: str = "tdm-renew-",
    ):
        self.executable: str = executable
        self.no_sandbox: bool = no_sandbox
        self.startup_timeout: float = startup_timeout
        # Renewal mints a proof and never needs a window; an interactive login
        # is the opposite - a visible page is the whole point, and a headless
        # one is exactly what Twitch's risk checks look for.
        self.headless: bool = headless
        self.extra_args: Sequence[str] = tuple(extra_args)
        # Only used to hand a child a DISPLAY; otherwise it inherits ours.
        self.env: Mapping[str, str] | None = env
        self.profile_prefix: str = profile_prefix

    async def _poll_ready(self, process: asyncio.subprocess.Process, profile: Path) -> str:
        while process.returncode is None:
            try:
                lines = (profile / "DevToolsActivePort").read_text().splitlines()
            except FileNotFoundError:
                await asyncio.sleep(.05)
                continue
            if (
                len(lines) != 2
                or not lines[0].isdecimal()
                or not 0 < int(lines[0]) < 65536
                or not re.fullmatch(r"/devtools/browser/[a-zA-Z0-9-]+", lines[1])
            ):
                raise SessionImportError("BROWSER_START")
            return f"http://127.0.0.1:{int(lines[0])}"
        raise SessionImportError("BROWSER_START")

    async def wait_ready(self, process: asyncio.subprocess.Process, profile: Path) -> str:
        # asyncio.timeout is 3.11+, and this fork still supports 3.10.
        try:
            return await asyncio.wait_for(
                self._poll_ready(process, profile), self.startup_timeout
            )
        except (TimeoutError, asyncio.TimeoutError):
            raise SessionImportError("BROWSER_START") from None

    @staticmethod
    def _terminate(process: asyncio.subprocess.Process) -> None:
        """Ask the browser and its children to exit."""
        with suppress(ProcessLookupError, OSError):
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGTERM)
            elif process.returncode is None:
                process.terminate()

    @staticmethod
    def _kill(process: asyncio.subprocess.Process) -> None:
        """
        Stop it outright.

        Windows has no SIGKILL, so the two platforms are spelled out rather than
        sharing one signal value - naming signal.SIGKILL there raises
        AttributeError, and even guarding it with suppress() would not help
        because the attribute is read before the call.
        """
        with suppress(ProcessLookupError, OSError):
            if os.name == "posix":
                os.killpg(process.pid, signal.SIGKILL)
            elif process.returncode is None:
                process.kill()

    @classmethod
    async def stop(cls, process: asyncio.subprocess.Process) -> None:
        cls._terminate(process)
        try:
            await asyncio.wait_for(process.wait(), 5)
        except TimeoutError:
            pass
        finally:
            # The leader can exit before descendants that ignore SIGTERM.
            cls._kill(process)
        if process.returncode is None:
            try:
                await asyncio.wait_for(process.wait(), 2)
            except TimeoutError:
                raise SessionImportError("BROWSER_STOP") from None

    @classmethod
    async def finish_stop(cls, process: asyncio.subprocess.Process) -> None:
        cleanup = asyncio.create_task(cls.stop(process))
        interrupted = False
        while not cleanup.done():
            try:
                await asyncio.shield(cleanup)
            except asyncio.CancelledError:
                interrupted = True
        try:
            cleanup.result()
        except SessionImportError:
            # Shutting the browser down failed. That is worth knowing, but it
            # must never replace the error that caused the shutdown - the
            # renewal itself may have failed for a reason worth reporting.
            logger.warning("The renewal browser did not shut down cleanly")
        if interrupted:
            raise asyncio.CancelledError

    @asynccontextmanager
    async def start(self) -> AsyncIterator[str]:
        process = None
        # Windows refuses to delete files a process still holds, and Chrome can
        # lag behind its own exit - a cleanup failure there must not turn into a
        # renewal failure.
        with tempfile.TemporaryDirectory(
            prefix=self.profile_prefix, ignore_cleanup_errors=True,
        ) as directory:
            profile = Path(directory)
            # Port zero, deliberately: naming the port ourselves makes Chrome
            # advertise navigator.webdriver=true, which is exactly the kind of
            # automation signal the integrity issuance must not carry. It is
            # also the only case where Chrome writes DevToolsActivePort, which
            # is how the real port is discovered.
            args = [
                self.executable, f"--user-data-dir={profile}",
                "--remote-debugging-address=127.0.0.1", "--remote-debugging-port=0",
                "--no-first-run", "--no-default-browser-check", "--disable-dev-shm-usage",
                "--disable-blink-features=AutomationControlled",
                *(() if self.headless else ("--window-size=1280,900", "--window-position=0,0")),
                *self.extra_args,
                "about:blank",
            ]
            if self.headless:
                args.insert(1, "--headless=new")
            if self.no_sandbox:
                args.insert(1, "--no-sandbox")
            try:
                process = await asyncio.create_subprocess_exec(
                    *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                    start_new_session=os.name == "posix",
                    **({} if self.env is None else {"env": {**os.environ, **self.env}}),
                )
                try:
                    address = await self.wait_ready(process, profile)
                except (OSError, ValueError, TimeoutError):
                    raise SessionImportError("BROWSER_START") from None
                yield address
            except OSError:
                raise SessionImportError("BROWSER_START") from None
            finally:
                if process is not None:
                    await self.finish_stop(process)
