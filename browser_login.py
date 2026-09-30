"""
Sign in to Twitch in a browser this app owns, and keep what comes out of it.

Twitch only hands out the full campaign catalogue to a token minted for its own
web client, and there is no login flow this app can complete by itself that
produces one. So a real browser is started here, on this machine, and the user
signs in through the page `login_server` serves: the browser's screen is
streamed to them and their mouse and keyboard are forwarded back into it.

Nothing is ever handed over. The browser that holds the credentials is the one
that produces them, on the same machine and the same address that will go on
using them - which is also what makes them trustworthy: what gets captured is
one complete request context, a token together with the integrity proof, device
id and user agent that were issued alongside it. That set is only valid
together, so it is captured as it was used, never reassembled.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import sys
from collections.abc import AsyncIterator, Callable, Mapping
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from time import time
from typing import Any

import aiohttp
from yarl import URL

from browser_cdp import (
    GQL_URL,
    INTEGRITY_URL,
    OwnedChromium,
    browser_target,
)
from constants import IMPORTED_SESSION_PATH
from session_import import (
    SDKCookie,
    ServerSeed,
    SessionBundle,
    PrivateSessionFile,
    probe_bundle,
    SessionImportError,
)


logger = logging.getLogger("TwitchDrops")

# One environment variable, for development: it points the whole flow at a local
# stand-in so it can be exercised without signing in to a real account.
_OVERRIDE = os.environ.get("TDM_LOGIN_URL", "")
LOGIN_URL = _OVERRIDE or "https://www.twitch.tv/login"
DROPS_URL = (
    str(URL(_OVERRIDE).with_path("/drops/campaigns")) if _OVERRIDE
    else "https://www.twitch.tv/drops/campaigns"
)

# The cookie Twitch sets once a sign-in has actually gone through. It is
# httpOnly, which is why it is read over the protocol rather than from the page.
AUTH_COOKIE = "auth-token"

# What a captured proof is assumed to be worth when Twitch never told us. The
# measured lifetime is around sixteen hours; claiming less only means the first
# renewal happens sooner, and renewal is the code path that keeps this alive.
FALLBACK_LIFETIME = 6 * 3600

# Long enough to find a phone, complete a 2FA prompt and read a captcha.
TOTAL_TIMEOUT = 1800.0
# How often the page is asked whether the sign-in has taken.
POLL_INTERVAL = 1.5
# The campaigns page is what makes the web client actually exchange tokens; a
# sign-in that has settled for this long is nudged onto it even if the user
# never presses the button.
NUDGE_AFTER = 8.0

FRAME_QUEUE = 2

# How long to give the sign-in page to replace the blank one before streaming
# it anyway, and how often to ask.
PAGE_WAIT = 5.0
PAGE_POLL = 0.1


def has_display() -> bool:
    """
    Whether a browser window has somewhere to go on this machine.

    Asked before anything is promised to the user: telling someone to open a
    URL and only then discovering there is no screen to draw on would leave
    them staring at a page that never fills in.
    """
    if os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"):
        return True
    return shutil.which("Xvfb") is not None


def has_visible_display() -> bool:
    """
    Whether someone can *see* a window on this machine, rather than merely
    have one opened on it.

    Not the same question as `has_display`: a headless server with Xvfb
    installed has somewhere for a window to go, and nobody sitting in front of
    it. That is the machine whose sign-in has to be reached over the network -
    here the window is in front of the user already, and sending them to an
    address as well is one step they should not have to take.
    """
    return bool(os.environ.get("DISPLAY")) or sys.platform in ("win32", "darwin")


@asynccontextmanager
async def virtual_display() -> AsyncIterator[str | None]:
    """
    A display to put a browser window on, starting one if the machine has none.

    A window is the whole point of this browser, and a headless one is the first
    thing Twitch's risk checks look for - so where there is no screen, Xvfb is
    started to act as one. Windows and macOS always have a desktop to draw on,
    and inherit its display rather than being handed one.
    """
    if os.environ.get("DISPLAY") or sys.platform in ("win32", "darwin"):
        yield None
        return
    executable = shutil.which("Xvfb")
    if executable is None:
        raise SessionImportError("BROWSER_DISPLAY")
    async with _xvfb(executable) as display:
        yield display


@asynccontextmanager
async def _xvfb(executable: str) -> AsyncIterator[str]:
    process = None
    try:
        for number in range(90, 110):
            if Path(f"/tmp/.X11-unix/X{number}").exists():
                continue
            # A fixed screen size keeps the captured frames predictable.
            process = await asyncio.create_subprocess_exec(
                executable, f":{number}", "-screen", "0", "1280x900x24", "-nolisten", "tcp",
                stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL,
                start_new_session=os.name == "posix",
            )
            if await _wait_for_socket(number, process):
                yield f":{number}"
                return
            # The number looked free but was taken between the check and the
            # start - a display this app does not own. Move on rather than
            # fighting over it.
            await _stop_process(process)
            process = None
        raise SessionImportError("BROWSER_DISPLAY")
    finally:
        if process is not None:
            await _stop_process(process)


async def _wait_for_socket(number: int, process: asyncio.subprocess.Process) -> bool:
    socket_ = Path(f"/tmp/.X11-unix/X{number}")
    for _ in range(100):
        if socket_.exists():
            return True
        if process.returncode is not None:
            return False
        await asyncio.sleep(.05)
    return False


async def _stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return
    with suppress(ProcessLookupError, OSError):
        process.terminate()
    try:
        await asyncio.wait_for(process.wait(), 5)
    except (TimeoutError, asyncio.TimeoutError):
        with suppress(ProcessLookupError, OSError):
            process.kill()
        await asyncio.gather(process.wait(), return_exceptions=True)


def _number(value: Any, default: float = 0.0) -> float:
    """Coerce anything a viewer sends into a coordinate, without trusting it."""
    if isinstance(value, bool):
        return default
    if isinstance(value, int):
        # Clamped as an integer: JSON allows an arbitrarily large number, and
        # float() raises on one that does not fit rather than returning infinity.
        return float(min(max(value, -10000), 10000))
    if not isinstance(value, float) or value != value or value in (float("inf"), float("-inf")):
        return default  # not a number, or NaN, or infinity
    return min(max(value, -10000.0), 10000.0)


class LoginObserver:
    """
    Watch a page that is signed in and work out which context it is using.

    This deliberately does not decide what Twitch will accept. It collects
    candidates; `probe_bundle` is the judge, and it is a real API call. Anything
    this class gets wrong shows up as a candidate that fails the probe, not as a
    broken session.
    """

    # Events that are not tied to a request have to be asked for by name; see
    # DevToolsConnection. The gql and integrity events arrive regardless.
    EVENTS = frozenset({"Page.screencastFrame"})

    def __init__(
        self, protocol: Any, *, on_frame: Callable[[dict[str, Any]], None],
        clock: Callable[[], float] = time,
    ):
        self.protocol: Any = protocol
        self.on_frame = on_frame
        self.clock = clock
        # The most recent gql request that was authenticated, and when it was
        # seen - the captured_at of the resulting bundle.
        self.headers: dict[str, str] | None = None
        self.user_agent: str | None = None
        self.seen_at: float | None = None
        # The body of the last /integrity response: the proof and, uniquely, its
        # expiry. The token itself is opaque and encrypted, so this response is
        # the only place the lifetime can be read from.
        self.proof: dict[str, Any] | None = None
        self.signed_in: bool = False
        self._watching: dict[str, str] = {}

    async def run(self) -> None:
        """Consume events until the connection closes."""
        while True:
            event = await self.protocol.events.get()
            if event is None:
                return
            method = event.get("method")
            params = event.get("params")
            if not isinstance(params, dict):
                continue
            if method == "Page.screencastFrame":
                self.on_frame(params)
                await self._ack(params)
            elif method == "Network.requestWillBeSent":
                self._request(params)
            elif method == "Network.loadingFinished":
                await self._finished(params)

    async def _ack(self, params: dict[str, Any]) -> None:
        """
        Acknowledge a frame, which is also what asks for the next one.

        Acknowledged whether or not anyone is watching: frames are only sent
        when the page changes, so a still page costs nothing, and a viewer that
        connects late gets the next frame rather than a stream that stalled
        waiting for an acknowledgement nobody was there to give.
        """
        session_id = params.get("sessionId")
        if not isinstance(session_id, int):
            return
        with suppress(SessionImportError, asyncio.TimeoutError):
            await self.protocol.command("Page.screencastFrameAck", {"sessionId": session_id})

    def _request(self, params: dict[str, Any]) -> None:
        request = params.get("request")
        if not isinstance(request, dict):
            return
        url = request.get("url")
        if url == INTEGRITY_URL:
            request_id = params.get("requestId")
            if isinstance(request_id, str):
                self._watching[request_id] = url
            return
        if url != GQL_URL:
            return
        headers = request.get("headers")
        cleaned = self._clean(headers)
        # A preflight carries no credentials and is not the context we are
        # after; requiring an authorization is what skips it.
        if not cleaned or "authorization" not in cleaned:
            return
        self.headers = cleaned
        self.user_agent = self._user_agent(headers) or self.user_agent
        self.seen_at = self.clock()
        self.signed_in = True

    async def _finished(self, params: dict[str, Any]) -> None:
        request_id = params.get("requestId")
        if not isinstance(request_id, str) or self._watching.pop(request_id, None) is None:
            return
        try:
            body = await self.protocol.body(request_id)
        except (SessionImportError, asyncio.TimeoutError, ValueError):
            return
        if (
            isinstance(body, dict)
            and isinstance(body.get("token"), str)
            and body["token"]
            and isinstance(body.get("expiration"), (int, float))
        ):
            self.proof = body

    @staticmethod
    def _clean(headers: Any) -> dict[str, str] | None:
        """
        Keep only what a captured context is allowed to contain.

        Anything else - and a browser sends a great deal else - would be
        rejected outright when the bundle is validated, so it is dropped here.
        The user agent is one of those: it is a field of its own in the bundle,
        not a header, even though it travels as one.
        """
        if not isinstance(headers, Mapping):
            return None
        cleaned: dict[str, str] = {}
        for name, value in headers.items():
            if not isinstance(name, str) or not isinstance(value, str):
                continue
            key = name.lower()
            if key in SessionBundle.HEADER_NAMES:
                cleaned[key] = value
        return cleaned or None

    @staticmethod
    def _user_agent(headers: Any) -> str | None:
        if not isinstance(headers, Mapping):
            return None
        for name, value in headers.items():
            if isinstance(name, str) and name.lower() == "user-agent" and isinstance(value, str):
                return value
        return None

    def candidates(self) -> list[tuple[dict[str, str], float | None]]:
        """
        What could be stored, most useful first, with an expiry when one is known.

        One is what the page was seen sending - a token and a proof known to
        work together, because they were used together. The other pairs the
        page's headers with the proof that was minted while we watched; it is
        the same pairing the renewal path builds, and it is used when the page's
        own requests predate the proof being issued.

        A known lifetime wins, because a proof stored without one has to be
        treated as expiring soon and renewed early. The rest is a preference
        order: whatever the probe rejects, the next candidate is tried.
        """
        headers = self.headers
        if not headers:
            return []
        found: list[tuple[dict[str, str], float | None]] = []
        proof = self.proof or {}
        proof_token = proof.get("token")
        expiry = proof.get("expiration")
        lifetime = float(expiry) / 1000 if isinstance(expiry, (int, float)) else None

        sent = headers.get("client-integrity")
        if sent:
            # The lifetime only applies if this is the proof that was minted for
            # these headers; a later one belongs to a different context.
            found.append((headers, lifetime if proof_token == sent else None))
        if isinstance(proof_token, str) and proof_token and proof_token != sent:
            found.append(({**headers, "client-integrity": proof_token}, lifetime))
        # Stable, so within equal lifetimes the page's own context stays first.
        return sorted(found, key=lambda candidate: candidate[1] is None)


class BrowserLogin:
    """One attempt at signing in, from a blank profile to a stored session."""

    def __init__(
        self, *, executable: str, on_accepted: Callable[[int], None],
        expected_user_id: Callable[[], int | None] = lambda: None,
        timeout: float = TOTAL_TIMEOUT, clock: Callable[[], float] = time,
        session_file: Path = IMPORTED_SESSION_PATH,
    ):
        self.executable: str = executable
        self.on_accepted = on_accepted
        self.expected_user_id = expected_user_id
        self.timeout: float = timeout
        self.clock = clock
        self._file = PrivateSessionFile(session_file)
        self._protocol: Any = None
        self._viewers: set[asyncio.Queue[dict[str, Any]]] = set()
        self._ready = asyncio.Event()
        self._cancelled = asyncio.Event()
        self._rejected: set[tuple[str, str]] = set()
        self._http: aiohttp.ClientSession | None = None
        self.user_agent: str = ""
        # Read by the viewer and by the status line.
        self.state: str = "starting"
        self.detail: str | None = None

    # -- what the viewer talks to ------------------------------------------

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=FRAME_QUEUE)
        self._viewers.add(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue[dict[str, Any]]) -> None:
        self._viewers.discard(queue)

    def _frame(self, params: dict[str, Any]) -> None:
        metadata = params.get("metadata") or {}
        frame = {
            "data": params.get("data"),
            "width": metadata.get("deviceWidth"),
            "height": metadata.get("deviceHeight"),
        }
        for queue in self._viewers:
            if queue.full():
                with suppress(asyncio.QueueEmpty):
                    queue.get_nowait()
            queue.put_nowait(frame)

    def mark_ready(self) -> None:
        """The user says the sign-in is done; stop waiting for more evidence."""
        self._ready.set()

    def cancel(self) -> None:
        self._cancelled.set()

    async def input(self, message: Mapping[str, Any]) -> None:
        """
        Apply one message from a viewer.

        A viewer is authenticated but is still a remote input: anything it
        sends may be malformed, and none of it may end the session.
        """
        protocol = self._protocol
        if protocol is None:
            return
        try:
            kind = message.get("t")
            if kind == "mouse":
                await self._mouse(protocol, message)
            elif kind == "key":
                await self._key(protocol, message)
            elif kind == "text":
                text = message.get("text")
                if isinstance(text, str) and text:
                    await protocol.command("Input.insertText", {"text": text[:4096]})
        except (SessionImportError, asyncio.TimeoutError, KeyError, TypeError, ValueError):
            logger.debug("Ignored an unusable viewer input")

    async def _mouse(self, protocol: Any, message: Mapping[str, Any]) -> None:
        kind = message.get("type")
        if kind not in ("mousePressed", "mouseReleased", "mouseMoved", "mouseWheel"):
            return
        params: dict[str, Any] = {
            "type": kind, "x": _number(message.get("x")), "y": _number(message.get("y")),
        }
        if kind == "mouseWheel":
            params["deltaX"] = _number(message.get("deltaX"))
            params["deltaY"] = _number(message.get("deltaY"))
        else:
            button = message.get("button")
            params["button"] = button if button in (
                "none", "left", "middle", "right", "back", "forward"
            ) else "left"
            click_count = message.get("clickCount")
            params["clickCount"] = (
                click_count if isinstance(click_count, int) and 0 < click_count < 4 else 1
            )
            params["buttons"] = 0 if kind == "mouseMoved" else (
                1 if params["button"] == "left" else 2
            )
        await protocol.command("Input.dispatchMouseEvent", params)

    async def _key(self, protocol: Any, message: Mapping[str, Any]) -> None:
        kind = message.get("type")
        if kind not in ("keyDown", "keyUp", "rawKeyDown", "char"):
            return
        params: dict[str, Any] = {"type": kind}
        for name in ("key", "code", "text", "unmodifiedText"):
            value = message.get(name)
            if isinstance(value, str) and len(value) <= 32:
                params[name] = value
        for name in ("windowsVirtualKeyCode", "nativeVirtualKeyCode", "modifiers", "location"):
            value = message.get(name)
            if isinstance(value, int) and not isinstance(value, bool) and 0 <= value < 1 << 16:
                params[name] = value
        if isinstance(message.get("autoRepeat"), bool):
            params["autoRepeat"] = message["autoRepeat"]
        await protocol.command("Input.dispatchKeyEvent", params)

    # -- the attempt -------------------------------------------------------

    def status(self) -> dict[str, Any]:
        return {"state": self.state, "detail": self.detail, "watching": len(self._viewers)}

    async def run(self) -> None:
        """
        Drive one sign-in to completion, or to a reason it did not happen.

        Success is signalled through `on_accepted`, exactly as an imported
        session used to be delivered, so the miner picks it up without a
        restart.
        """
        # Chromium refuses its sandbox when running as root, which is the normal
        # case in a container.
        no_sandbox = os.name == "posix" and os.geteuid() == 0
        self._http = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            cookie_jar=aiohttp.DummyCookieJar(),
            headers={"Accept": "*/*", "Accept-Encoding": "gzip"},
        )
        try:
            async with virtual_display() as display:
                browser = OwnedChromium(
                    self.executable, no_sandbox=no_sandbox, headless=False,
                    env={} if display is None else {"DISPLAY": display},
                    profile_prefix="tdm-login-",
                )
                async with browser.start() as address:
                    async with browser_target(
                        address, extra_events=LoginObserver.EVENTS, drop_oldest=True,
                    ) as protocol:
                        self._protocol = protocol
                        try:
                            await self._collect(protocol)
                        finally:
                            self._protocol = None
        except SessionImportError as error:
            self._fail(error.code)
            raise
        except (asyncio.TimeoutError, OSError) as error:
            # A browser or a socket that stopped answering. The attempt is over
            # either way, and it has to say so: left alone it would look like a
            # failure with no reason, or worse, like nothing happening at all.
            self._fail("BROWSER_PROTOCOL")
            raise SessionImportError("BROWSER_PROTOCOL") from error
        finally:
            with suppress(Exception):
                await self._http.close()
            self._http = None

    async def _collect(self, protocol: Any) -> None:
        self.state = "waiting"
        observer = LoginObserver(protocol, on_frame=self._frame, clock=self.clock)
        watching = asyncio.create_task(observer.run())
        try:
            await protocol.command("Page.enable")
            await protocol.command("Network.enable")
            # Read once: it does not change, and a capture still prefers the
            # value the page actually sent over anything read beforehand.
            result = await protocol.command(
                "Runtime.evaluate", {"expression": "navigator.userAgent", "returnByValue": True}
            )
            self.user_agent = str(result["result"].get("value") or "")
            # Navigated before the capture starts, deliberately. The target is
            # created on about:blank, and starting the stream first would send
            # that empty page as the first frame - a white flash before the
            # sign-in page, which is the one thing the user is waiting to see.
            await protocol.command("Page.navigate", {"url": LOGIN_URL})
            await self._wait_for_page(protocol)
            await protocol.command("Page.startScreencast", {
                "format": "jpeg", "quality": 60,
                "maxWidth": 1280, "maxHeight": 900, "everyNthFrame": 1,
            })

            deadline = self.clock() + self.timeout
            settled_at: float | None = None
            nudged = False
            while True:
                if self._cancelled.is_set():
                    raise SessionImportError("LOGIN_CANCELLED")
                if self.clock() >= deadline:
                    raise SessionImportError("LOGIN_TIMEOUT")
                if watching.done():
                    # The browser or its connection went away under us.
                    raise SessionImportError("LOGIN_CLOSED")

                signed_in = observer.signed_in or await self._has_auth_cookie(protocol)
                if signed_in:
                    self.state = "signed_in"
                    if settled_at is None:
                        settled_at = self.clock()

                if not nudged and self._should_nudge(settled_at):
                    # The web client only exchanges tokens over gql once it is
                    # asked for something; the campaigns page is the thing that
                    # asks, and it holds the data this login is for.
                    nudged = True
                    with suppress(SessionImportError, asyncio.TimeoutError):
                        await protocol.command("Page.navigate", {"url": DROPS_URL})

                if signed_in or self._ready.is_set():
                    for headers, expiry in observer.candidates():
                        if await self._accept(headers, expiry, observer):
                            # Stored and handed over; this attempt is done.
                            return

                await asyncio.sleep(POLL_INTERVAL)
        finally:
            watching.cancel()
            await asyncio.gather(watching, return_exceptions=True)

    async def _wait_for_page(self, protocol: Any) -> None:
        """
        Wait until the tab is showing the page rather than the blank one.

        The browser refuses to start a screen capture while it is swapping the
        new page in - it answers "Not attached to an active page" - and the swap
        is quick but not instant. Asking the document where it is, is the
        cheapest honest way to tell "there" from "still on about:blank", and it
        does not care where the page redirected to on the way.
        """
        deadline = self.clock() + PAGE_WAIT
        while self.clock() < deadline:
            try:
                result = await protocol.command("Runtime.evaluate", {
                    "expression": "document.location.href", "returnByValue": True})
            except (SessionImportError, asyncio.TimeoutError):
                return
            href = result["result"].get("value")
            if isinstance(href, str) and href and not href.startswith("about:"):
                return
            await asyncio.sleep(PAGE_POLL)
        # Not there yet, but the capture is worth attempting anyway: whatever
        # went wrong, leaving the user with nothing at all is worse.

    def _should_nudge(self, settled_at: float | None) -> bool:
        if self._ready.is_set():
            return True
        return settled_at is not None and self.clock() - settled_at >= NUDGE_AFTER

    async def _has_auth_cookie(self, protocol: Any) -> bool:
        try:
            result = await protocol.command("Network.getCookies", {"urls": [LOGIN_URL]})
        except (SessionImportError, asyncio.TimeoutError):
            return False
        cookies = result.get("cookies")
        if not isinstance(cookies, list):
            return False
        return any(
            isinstance(cookie, dict) and cookie.get("name") == AUTH_COOKIE and cookie.get("value")
            for cookie in cookies
        )

    async def _accept(
        self, headers: dict[str, str], expiry: float | None, observer: LoginObserver,
    ) -> bool:
        """
        Try one candidate: store it and report True if Twitch accepts it.

        The probe is what makes this safe. A candidate that can read the
        campaign catalogue is one that works, so there is no need to be sure of
        it beforehand - and one that cannot is discarded without touching the
        stored session.
        """
        identity = (headers.get("authorization", ""), headers.get("client-integrity", ""))
        if identity in self._rejected:
            # Already tried and refused. Probing again on the next poll would
            # mean asking Twitch the same question every couple of seconds.
            return False

        captured_at = observer.seen_at or self.clock()
        try:
            bundle = SessionBundle.from_dict({
                "version": 1,
                "captured_at": captured_at,
                "expires_at": expiry if expiry is not None else captured_at + FALLBACK_LIFETIME,
                "user_agent": observer.user_agent or self.user_agent,
                "headers": headers,
            }, now=self.clock())
        except SessionImportError as error:
            self._rejected.add(identity)
            logger.info(f"Discarded a captured login context ({error.code})")
            return False
        if bundle.expires_at <= self.clock():
            # Expired between being used and being read; the page will mint
            # another one shortly.
            self._rejected.add(identity)
            return False

        cookie = await self._sdk_cookie()
        if self._http is None:
            return False
        try:
            user_id = await probe_bundle(bundle, self._http)
        except SessionImportError as error:
            self._rejected.add(identity)
            logger.info(f"Twitch did not accept a captured login context ({error.code})")
            return False
        except (asyncio.TimeoutError, OSError):
            # Not a verdict on the candidate - a slow link is not a rejection,
            # so it stays a candidate and the next round asks again. Ending the
            # sign-in here would tear the browser out from under someone whose
            # link merely stalled.
            logger.info("Could not reach Twitch to check a captured login context")
            return False

        expected = self.expected_user_id()
        if expected is not None and expected != user_id:
            # Switching accounts mid-run would leave the user id baked into
            # websocket topics and cached payloads pointing at the old one.
            raise SessionImportError("ACCOUNT_MISMATCH")

        self._file.write(ServerSeed(bundle, cookie))
        self.state = "captured"
        self.detail = None
        logger.info(
            f"Signed in as user ID {user_id}; the session is valid for"
            f" {(bundle.expires_at - self.clock()) / 3600:.1f}h"
        )
        self.on_accepted(user_id)
        return True

    async def _sdk_cookie(self) -> SDKCookie | None:
        """
        The cookie renewal runs on.

        Only renewal needs it, so a missing or unreadable one costs the ability
        to renew rather than the whole login - the same trade the import path
        makes.
        """
        protocol = self._protocol
        if protocol is None:
            return None
        try:
            result = await protocol.command("Network.getCookies", {"urls": [SDKCookie.URL]})
            return SDKCookie.from_browser(result.get("cookies"), now=self.clock())
        except SessionImportError as error:
            logger.warning(
                f"The captured session cannot be renewed ({error.code}) - it will stop"
                f" working when it expires"
            )
            return None
        except (asyncio.TimeoutError, TypeError, AttributeError):
            logger.warning("The captured session cannot be renewed (SDK_COOKIE)")
            return None

    def _fail(self, code: str) -> None:
        self.state = "failed"
        self.detail = code
