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
import time
from collections import deque
from collections.abc import AsyncIterator, Mapping, Sequence
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Any, Protocol

import aiohttp
from yarl import URL

from twitchdropsminer.auth.session_import import SessionImportError


logger = logging.getLogger("TwitchDrops")

# The maximum amount of data we are willing to have buffered for one reply.
MAX_MESSAGE_BYTES = 16 * 1024 * 1024

# The endpoints this module reasons about; see DevToolsConnection.
GQL_URL = "https://gql.twitch.tv/gql"
INTEGRITY_URL = "https://gql.twitch.tv/integrity"

# How long the browser is given to close itself over the protocol, then to exit
# after SIGTERM, then after SIGKILL. Closing over the protocol first is what
# lets Chrome shut its children down and reap them: a browser killed by a
# signal does not, and its children end up parentless.
CLOSE_TIMEOUT = 3.0
CLOSE_REQUEST_TIMEOUT = 1.5
TERM_TIMEOUT = 1.5
KILL_TIMEOUT = 1.5

# The names every temporary profile here gets: the prefix `TemporaryDirectory`
# was given plus the eight characters it appends. They are how a browser and its
# profile, left behind by an earlier run, are told apart from anything else.
PROFILE_PREFIXES = ("tdm-renew-", "tdm-login-")
_PROFILE_NAME = re.compile(r"tdm-(?:renew|login)-[A-Za-z0-9_]{6,16}")

# A profile is only removed without a browser around once it is older than any
# session could legitimately last; a sign-in gets TOTAL_TIMEOUT (30 minutes) to
# be completed, and renewal a couple of minutes. Anything younger may belong to
# a browser still starting or in progress elsewhere.
PROFILE_MAX_AGE = 2 * 3600.0

# Linux: ask the kernel to SIGKILL a child when this process dies. Nothing else
# can stop a browser when the miner itself is SIGKILLed - no cleanup runs - and
# the result is a window, or a whole headless browser, that outlives the miner
# that owned it. Resolved once, at import, so the forked child only has to call
# one already-loaded symbol.
_PR_SET_PDEATHSIG = 1
_PARENT_PID = os.getpid()
try:
    import ctypes

    _prctl = ctypes.CDLL(None, use_errno=True).prctl
except (ImportError, OSError, AttributeError):  # not Linux, or no libc
    _prctl = None


def _die_with_parent() -> None:
    """
    Child side of a spawn on Linux: die when the miner does.

    Runs between fork and exec, so it stays tiny and lock-free - dlopen and
    imports are exactly what must not happen there, which is why `_prctl` was
    resolved before any thread existed. `subprocess` documents preexec_fn as
    unsafe in a threaded process; the call below is a single libc syscall
    wrapper, and the alternative is a browser that survives a hard kill.
    """
    if _prctl is not None:
        _prctl(_PR_SET_PDEATHSIG, signal.SIGKILL, 0, 0, 0)
        # The miner may have died between fork and the call above, in which
        # case no signal will ever come: get out instead of lingering.
        if os.getppid() != _PARENT_PID:
            os._exit(127)


# None on platforms where it does not apply; subprocess rejects only non-None.
PREEXEC = _die_with_parent if os.name == "posix" and _prctl is not None else None


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
        for variable in ("ProgramFiles", "ProgramFiles(x86)", "LOCALAPPDATA"):
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


def _process_fields(pid: int) -> list[str] | None:
    """
    The fields of /proc/<pid>/stat after the command name, or None.

    The command name can contain spaces and parentheses, so everything up to
    the last ')' is skipped rather than split on whitespace: the remaining
    fields start with state, ppid, pgrp and session, which is all this module
    needs.
    """
    try:
        stat = Path("/proc", str(pid), "stat").read_text()
        return stat.rsplit(")", 1)[1].split()
    except (OSError, IndexError, ValueError):
        return None


def _group_members(pgid: int) -> list[int]:
    """Live (not zombie) processes still in a process group."""
    members: list[int] = []
    try:
        entries = os.listdir("/proc")
    except OSError:
        return members
    for entry in entries:
        if not entry.isdigit():
            continue
        fields = _process_fields(int(entry))
        # state, ppid, pgrp, session
        if fields is None or len(fields) < 3:
            continue
        if fields[2] != str(pgid) or fields[0] == "Z":
            continue
        members.append(int(entry))
    return members


# Children whose exit asyncio is waiting for. The reaper below must never
# consume one of those itself: the status belongs to `process.wait()`.
_SPAWNED: set[int] = set()


def track_child(pid: int) -> None:
    _SPAWNED.add(pid)


def untrack_child(pid: int) -> None:
    _SPAWNED.discard(pid)


def reap_orphans() -> list[int]:
    """
    Reap zombie children nobody else is waiting for.

    When the miner is PID 1 (a container running it directly), every process
    orphaned by a browser or by a crashed worker is reparented to it, and
    Python reaps only the children it spawned - so without this they stay in
    `top` as zombies for the life of the container. Elsewhere this finds only
    children of the current process, and a running browser is not a zombie.
    """
    reaped: list[int] = []
    if os.name != "posix" or not os.path.isdir("/proc"):
        return reaped
    me = str(os.getpid())
    for entry in os.listdir("/proc"):
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid in _SPAWNED:
            continue  # asyncio owns this one's exit status
        fields = _process_fields(pid)
        if fields is None or len(fields) < 2:
            continue
        if fields[0] != "Z" or fields[1] != me:
            continue
        try:
            os.waitpid(pid, os.WNOHANG)
            reaped.append(pid)
        except (ChildProcessError, OSError):
            continue
    if reaped:
        logger.debug(
            "Reaped zombie child processes: "
            + ", ".join(str(pid) for pid in reaped)
        )
    return reaped


def _is_owned_profile(name: str) -> bool:
    """Whether a directory name is one of this app's temporary profiles."""
    return _PROFILE_NAME.fullmatch(name) is not None


def _profile_directories() -> list[Path]:
    """Every temporary browser profile in the temp directory."""
    base = Path(tempfile.gettempdir())
    try:
        entries = list(base.iterdir())
    except OSError:
        return []
    return [
        path for path in entries
        # A link is not a profile, and following one would delete somewhere
        # else entirely.
        if not path.is_symlink() and path.is_dir() and _is_owned_profile(path.name)
    ]


def _profiles_in_use() -> set[str]:
    """Profile paths named by a live process's command line."""
    used: set[str] = set()
    try:
        entries = os.listdir("/proc")
    except OSError:
        return used
    for entry in entries:
        if not entry.isdigit():
            continue
        try:
            arguments = Path("/proc", entry, "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        for argument in arguments:
            text = argument.decode("utf8", "replace")
            if text.startswith("--user-data-dir="):
                used.add(os.path.realpath(text.split("=", 1)[1]))
                break
    return used


def _remove_profile(directory: str | Path, *, older_than: float | None = None) -> bool:
    """Delete one temporary profile, if it really is one of ours."""
    path = Path(directory)
    if path.is_symlink() or not path.is_dir() or not _is_owned_profile(path.name):
        return False
    try:
        if older_than is not None and time.time() - path.stat().st_mtime < older_than:
            return False
        shutil.rmtree(path)
        return True
    except OSError:
        # A file that appeared while the directory was being walked, or one
        # this user may not remove. Either way it is not worth a failure.
        return False


def clean_stale_profiles(max_age: float = PROFILE_MAX_AGE) -> list[str]:
    """
    Remove temporary browser profiles that no browser is using.

    `TemporaryDirectory` removes a profile when its browser is stopped the
    ordinary way, but a hard-killed miner never runs that cleanup - and each
    profile is a few hundred megabytes. A startup sweep is the only thing that
    reclaims the disk those sessions leave behind.
    """
    used = _profiles_in_use()
    removed: list[str] = []
    for path in _profile_directories():
        if os.path.realpath(path) in used:
            continue
        if _remove_profile(path, older_than=max_age):
            removed.append(str(path))
    if removed:
        logger.info(
            "Removed temporary browser profiles left behind by an earlier run: "
            + ", ".join(removed)
        )
    return removed


def kill_orphaned_browsers() -> list[int]:
    """
    Kill browsers that an earlier run left behind.

    A browser is only ours to kill when its whole process group carries one of
    this app's temporary profiles as its user-data directory and its parent is
    gone (PID 1). That is a browser no miner owns any more; a browser a running
    instance is using right now still has that miner as its parent and is left
    alone.

    Without this, a miner restarted after a hard kill keeps the previous run's
    browser alive - possibly sitting on Twitch, burning CPU, until someone
    notices it in `top`.
    """
    killed: list[int] = []
    if not sys.platform.startswith("linux"):
        return killed
    try:
        entries = os.listdir("/proc")
    except OSError:
        return killed
    for entry in entries:
        if not entry.isdigit():
            continue
        pid = int(entry)
        if pid == os.getpid():
            continue
        fields = _process_fields(pid)
        # state, ppid, pgrp: an orphaned session/pgroup leader, and not a
        # zombie somebody else has yet to reap.
        if fields is None or len(fields) < 3:
            continue
        if fields[0] == "Z" or fields[1] != "1" or fields[2] != str(pid):
            continue
        try:
            cmdline = Path("/proc", entry, "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        profile = ""
        for argument in cmdline:
            text = argument.decode("utf8", "replace")
            if text.startswith("--user-data-dir="):
                profile = text.split("=", 1)[1].rstrip("/")
                break
        if not _is_owned_profile(os.path.basename(profile)):
            continue
        with suppress(ProcessLookupError, OSError):
            os.killpg(pid, signal.SIGKILL)
            killed.append(pid)
        # The profile is a few hundred megabytes. The process that would have
        # removed it is the one just killed, so do it here.
        _remove_profile(profile)
    if killed:
        logger.info(
            "Closed browser processes left behind by an earlier run: "
            + ", ".join(str(pid) for pid in killed)
        )
    return killed


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
        self, executable: str, *, no_sandbox: bool | None = None,
        startup_timeout: float = 40, headless: bool = True,
        extra_args: Sequence[str] = (), env: Mapping[str, str] | None = None,
        profile_prefix: str = "tdm-renew-", proxy: str = "", user_agent: str = "",
    ):
        self.executable: str = executable
        # Chromium refuses its sandbox when running as root, which is the normal
        # case in a container, and refuses to start at all rather than degrade.
        # Decided here rather than at each call site: every launcher - renewal,
        # sign-in and the browser check - has to get this right, and one that
        # forgets fails with BROWSER_START on exactly the machines that cannot
        # pop a window to notice it.
        if no_sandbox is None:
            no_sandbox = os.name == "posix" and os.geteuid() == 0
        self.no_sandbox: bool = no_sandbox
        self.startup_timeout: float = startup_timeout
        # A headless browser advertises "HeadlessChrome" in its default user
        # agent, and Twitch's integrity issuance is exactly the kind of thing
        # that refuses to mint for it. Renewal passes the user agent captured
        # with the session so the context stays the one Twitch accepted.
        self.user_agent: str = user_agent
        # The browser does not read the miner's requests' proxy setting, so it
        # has to be handed over explicitly; Twitch's SDK and integrity endpoint
        # are unreachable for a browser behind a proxy that is not told about it.
        self.proxy: str = proxy
        # Renewal mints a proof and never needs a window; an interactive login
        # is the opposite - a visible page is the whole point, and a headless
        # one is exactly what Twitch's risk checks look for.
        self.headless: bool = headless
        self.extra_args: Sequence[str] = tuple(extra_args)
        # Only used to hand a child a DISPLAY; otherwise it inherits ours.
        self.env: Mapping[str, str] | None = env
        self.profile_prefix: str = profile_prefix

    async def _poll_ready(
        self, process: asyncio.subprocess.Process, profile: Path,
    ) -> tuple[str, URL]:
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
            port = int(lines[0])
            address = f"http://127.0.0.1:{port}"
            # The browser-level socket, kept so the browser can be asked to
            # close itself rather than be killed. Validated like every other
            # endpoint before anything dials it.
            endpoint = local_endpoint(
                address, f"ws://127.0.0.1:{port}{lines[1]}"
            )
            return address, endpoint
        raise SessionImportError("BROWSER_START")

    async def wait_ready(
        self, process: asyncio.subprocess.Process, profile: Path,
    ) -> tuple[str, URL]:
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
    async def _request_close(cls, endpoint: URL) -> bool:
        """
        Ask Chrome to close itself over the debugging socket.

        This is the difference between a browser that shuts its children down
        and reaps them, and one that is shot in the head: a signal-killed
        browser leaves its renderers, GPU and utility processes parentless, and
        where nothing reaps them they stay in `top` as zombies. Returns whether
        the request could be delivered - failure is not an error, the signal
        path below always follows, it just has nothing to wait for.
        """
        try:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=CLOSE_REQUEST_TIMEOUT)
            ) as http:
                async with http.ws_connect(
                    endpoint, timeout=aiohttp.ClientWSTimeout(ws_close=1),
                ) as socket_:
                    await socket_.send_json(
                        {"id": 1, "method": "Browser.close", "params": {}}
                    )
            return True
        except (aiohttp.ClientError, asyncio.TimeoutError, OSError, ValueError):
            return False

    @classmethod
    async def _wait_group_gone(cls, pgid: int, timeout: float) -> bool:
        """Whether every live member of a process group has exited."""
        deadline = asyncio.get_running_loop().time() + timeout
        while True:
            if sys.platform.startswith("linux"):
                if not _group_members(pgid):
                    return True
            else:
                # No /proc: the group is gone once the kernel says it does not
                # exist. Zombies count as existing, but only until they are
                # reaped, which is prompt where this branch is used.
                try:
                    os.killpg(pgid, 0)
                except ProcessLookupError:
                    return True
            now = asyncio.get_running_loop().time()
            if now >= deadline:
                return False
            await asyncio.sleep(min(.1, deadline - now))

    @classmethod
    async def _finish_group(cls, pgid: int) -> None:
        """
        Make sure nothing the browser started outlives it.

        The leader is already gone when this runs. Children are in the same
        process group - the browser was started as a session leader - so after
        a protocol close they are normally gone too, and the signal path here
        costs one check. If a child survived (a tab that refused to close, a
        helper that ignores SIGTERM) it is stopped now, rather than being left
        behind as a parentless process.
        """
        if os.name != "posix":
            return  # Chrome's children die with it through a Windows job object
        if await cls._wait_group_gone(pgid, 0):
            return
        for number, timeout in ((signal.SIGTERM, 1.0), (signal.SIGKILL, KILL_TIMEOUT)):
            with suppress(ProcessLookupError, OSError):
                os.killpg(pgid, number)
            if await cls._wait_group_gone(pgid, timeout):
                return
        raise SessionImportError("BROWSER_STOP")

    @classmethod
    async def stop(
        cls, process: asyncio.subprocess.Process, endpoint: URL | None = None,
    ) -> None:
        """
        Close the browser, escalate only as far as needed, then check its group.

        The order matters. A protocol close lets Chrome shut down and reap its
        own children; SIGTERM and SIGKILL are fallbacks for a browser too wedged
        to answer. Killing first - which is what this used to do - is what made
        every stop scatter parentless Chrome processes behind it.
        """
        if endpoint is not None and process.returncode is None:
            requested = await cls._request_close(endpoint)
            # Even an undeliverable request means the browser may already be on
            # its way out - its page target was closed a moment ago - and
            # signalling it now would abort its own cleanup.
            if process.returncode is None:
                try:
                    await asyncio.wait_for(
                        process.wait(), CLOSE_TIMEOUT if requested else 1.0
                    )
                except (TimeoutError, asyncio.TimeoutError):
                    pass
        if process.returncode is None:
            cls._terminate(process)
            try:
                await asyncio.wait_for(process.wait(), TERM_TIMEOUT)
            except (TimeoutError, asyncio.TimeoutError):
                pass
        if process.returncode is None:
            cls._kill(process)
            try:
                await asyncio.wait_for(process.wait(), KILL_TIMEOUT)
            except (TimeoutError, asyncio.TimeoutError):
                pass
        if process.returncode is None:
            raise SessionImportError("BROWSER_STOP")
        try:
            await cls._finish_group(process.pid)
        finally:
            # Any child the browser shed on its way out has just died with it;
            # collect those now rather than leaving entries in `top` forever.
            reap_orphans()

    @classmethod
    async def finish_stop(
        cls, process: asyncio.subprocess.Process, endpoint: URL | None = None,
    ) -> None:
        cleanup = asyncio.create_task(cls.stop(process, endpoint))
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

    @staticmethod
    def _log_start_failure(
        error: SessionImportError, profile: Path, tail: deque[str]
    ) -> None:
        detail = " | ".join(tail)
        # Carried on the exception so a diagnostic command can show it too.
        error.detail = detail  # type: ignore[attr-defined]
        logger.warning(
            f"Browser start failed ({error.code}) using profile {profile}"
            + (f" - {detail}" if detail else " - the browser produced no output")
        )

    @asynccontextmanager
    async def start(self) -> AsyncIterator[str]:
        process = None
        endpoint: URL | None = None
        # Chrome's own diagnostics are the only clue when it refuses to open
        # the debugging port (a policy, a wrapper script, a missing DLL). Keep
        # a bounded tail and only surface it when starting fails.
        tail: deque[str] = deque(maxlen=25)

        async def drain(stream: asyncio.StreamReader) -> None:
            while True:
                try:
                    line = await stream.readline()
                except (asyncio.CancelledError, OSError):
                    return
                if not line:
                    return
                text = line.decode("utf8", "replace").rstrip()
                if text:
                    tail.append(text)

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
                "--enable-logging=stderr",
                *(() if self.headless else ("--window-size=1280,900", "--window-position=0,0")),
                *((f"--proxy-server={self.proxy}",) if self.proxy else ()),
                *((f"--user-agent={self.user_agent}",) if self.user_agent else ()),
                *self.extra_args,
                "about:blank",
            ]
            if self.headless:
                args.insert(1, "--headless=new")
            if self.no_sandbox:
                args.insert(1, "--no-sandbox")
            drain_task: asyncio.Task | None = None
            try:
                logger.info(
                    f"Starting the {'headless' if self.headless else 'sign-in'}"
                    f" browser: {self.executable}"
                )
                if self.proxy:
                    # Never put proxy credentials in the log.
                    logger.info(
                        "Browser proxy: "
                        + re.sub(r"//[^/@]+@", "//", self.proxy)
                    )
                process = await asyncio.create_subprocess_exec(
                    *args, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
                    start_new_session=os.name == "posix", preexec_fn=PREEXEC,
                    **({} if self.env is None else {"env": {**os.environ, **self.env}}),
                )
                track_child(process.pid)
                if process.stderr is not None:
                    drain_task = asyncio.create_task(drain(process.stderr))
                try:
                    address, endpoint = await self.wait_ready(process, profile)
                except SessionImportError as error:
                    self._log_start_failure(error, profile, tail)
                    raise
                except (OSError, ValueError, TimeoutError):
                    error = SessionImportError("BROWSER_START")
                    self._log_start_failure(error, profile, tail)
                    raise error from None
                yield address
            except OSError:
                error = SessionImportError("BROWSER_START")
                self._log_start_failure(error, profile, tail)
                raise error from None
            finally:
                if drain_task is not None:
                    drain_task.cancel()
                    with suppress(asyncio.CancelledError, Exception):
                        await drain_task
                if process is not None:
                    try:
                        await self.finish_stop(process, endpoint)
                    finally:
                        untrack_child(process.pid)
