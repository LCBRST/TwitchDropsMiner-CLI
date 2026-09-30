"""
The one listening socket: a page that shows a browser, and the browser itself.

Signing in needs a real browser window on this machine, but the person doing it
is often somewhere else - a headless box in a cupboard, a container, a server
with no screen. So the browser's screen is streamed to a page served from here,
and the mouse and keyboard coming back from that page are fed into it. What the
user is looking at is not a copy of Twitch rendered in their own browser; it is
the miner's browser, at the miner's address, which is exactly why the session it
ends up holding is one the miner can go on using.

The page is reachable by anyone who can reach the port, so it is protected by a
token that exists only in the URL that gets printed, and it stops listening as
soon as a session is in.
"""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
from contextlib import suppress
from html import escape
from pathlib import Path
from time import time
from typing import Any, Callable

import aiohttp
from aiohttp import web
from yarl import URL

from browser_login import BrowserLogin
from constants import IMPORTED_SESSION_PATH
from session_import import SessionImportError
from translate import _
from utils import WILDCARD_HOSTS, local_ipv4_addresses


logger = logging.getLogger("TwitchDrops")

COOKIE_NAME = "tdm_login"
# Viewer input is a handful of numbers per event; nothing legitimate is larger.
MAX_INPUT_BYTES = 64 * 1024


class _Rejected(Exception):
    """Internal carrier for a prepared error response."""

    def __init__(self, status: int, detail: str):
        self.status: int = status
        self.detail: str = detail
        super().__init__(detail)


# Why a browser sign-in could not be started, as translation keys. Both the
# automatic start and the command report these, so they are mapped in one place.
START_REASONS = {
    "no_browser": ("cli", "signin", "no_browser"),
    "no_display": ("cli", "signin", "no_display"),
    "bind_failed": ("cli", "signin", "bind_failed"),
}


def start_reason(code: str) -> str:
    """
    Say why a browser sign-in could not be started.

    Never shows a bare code, and never raises on one this build does not know -
    a newer one could always turn up.
    """
    path = START_REASONS.get(code)
    if path is None:
        return _("cli", "commands", "login_unavailable_unknown")
    return _(*path)


def _port(url: URL) -> int:
    """The port a URL actually means, whether or not it was written out."""
    if url.port is not None:
        return url.port
    return 443 if url.scheme == "https" else 80


def _page(strings: dict[str, str]) -> str:
    """
    The viewer page.

    Kept here rather than in a file of its own: the build ships `lang/*.json`
    and nothing else, so anything else would mean teaching both build scripts
    about it. The same reasoning as the stub page renewal navigates to.

    Frames arrive as base64 JPEG over the socket and are drawn to a canvas, so
    a slow client drops frames instead of queueing them up and playing a
    stutter of everything that happened while it was behind.
    """
    # A string that happened to contain a tag could otherwise break out of the
    # script element the whole set is delivered in.
    payload = json.dumps(strings).replace("<", "\\u003c")
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{escape(strings["page_title"])}</title>
<style>
  :root {{ color-scheme: dark }}
  body {{ margin:0; background:#18181b; color:#efeff1;
          font:15px/1.5 system-ui,-apple-system,Segoe UI,Roboto,sans-serif }}
  header {{ display:flex; gap:12px; align-items:center; padding:10px 14px;
            background:#0e0e10; border-bottom:1px solid #2f2f35; flex-wrap:wrap }}
  #status {{ flex:1; min-width:12em }}
  button {{ font:inherit; padding:7px 14px; border-radius:6px; border:1px solid #3a3a41;
            background:#26262c; color:#efeff1; cursor:pointer }}
  button:hover {{ background:#32323a }}
  button:disabled {{ opacity:.45; cursor:default }}
  #screen {{ position:relative; background:#000; outline:none; min-height:420px }}
  canvas {{ display:block; width:100%; height:auto; cursor:default }}
  /* Until the first frame arrives there is nothing to look at, so the area
     says what is happening instead of sitting there black. */
  #waiting {{ position:absolute; inset:0; display:flex; align-items:center;
              justify-content:center; color:#adadb8 }}
  #screen.started #waiting {{ display:none }}
  p {{ margin:10px 14px; color:#adadb8 }}
</style></head>
<body>
<header>
  <span id="status"></span>
  <button id="finish"></button>
  <button id="cancel"></button>
</header>
<div id="screen" tabindex="0">
  <div id="waiting"></div>
  <canvas id="view" width="1280" height="756"></canvas>
</div>
<p id="hint"></p>
<script id="strings" type="application/json">{payload}</script>
<script>
"use strict";
const S = JSON.parse(document.getElementById("strings").textContent);
const canvas = document.getElementById("view");
const ctx = canvas.getContext("2d");
const screenEl = document.getElementById("screen");
const statusEl = document.getElementById("status");
const finishEl = document.getElementById("finish");
const cancelEl = document.getElementById("cancel");
document.getElementById("hint").textContent = S.page_hint;
document.getElementById("waiting").textContent = S.page_starting;

let socket = null;
let done = false;
let lastMove = 0;
const decoder = new Image();
decoder.onload = () => {{
  if (canvas.width !== decoder.naturalWidth || canvas.height !== decoder.naturalHeight) {{
    canvas.width = decoder.naturalWidth;
    canvas.height = decoder.naturalHeight;
  }}
  ctx.drawImage(decoder, 0, 0);
}};

function send(message) {{
  if (socket && socket.readyState === 1) socket.send(JSON.stringify(message));
}}

function connect() {{
  const scheme = location.protocol === "https:" ? "wss://" : "ws://";
  socket = new WebSocket(scheme + location.host + "/login/ws");
  socket.onmessage = (event) => {{
    const message = JSON.parse(event.data);
    if (message.data) {{
      decoder.src = "data:image/jpeg;base64," + message.data;
      screenEl.classList.add("started");
    }}
  }};
  socket.onclose = () => {{
    if (done) return;
    statusEl.textContent = S.page_disconnected;
    setTimeout(connect, 1000);
  }};
}}

// The image is scaled to the page, so screen coordinates have to be mapped
// back onto the browser's own, which is what the protocol takes.
function place(event) {{
  const rect = canvas.getBoundingClientRect();
  return {{
    x: (event.clientX - rect.left) * (canvas.width / rect.width),
    y: (event.clientY - rect.top) * (canvas.height / rect.height),
  }};
}}
const BUTTONS = ["left", "middle", "right"];
function modifiers(event) {{
  return (event.altKey ? 1 : 0) | (event.ctrlKey ? 2 : 0)
       | (event.metaKey ? 4 : 0) | (event.shiftKey ? 8 : 0);
}}
function mouse(type, event, clickCount) {{
  const at = place(event);
  send({{t: "mouse", type: type, x: at.x, y: at.y,
         button: BUTTONS[event.button] || "left", clickCount: clickCount || 1}});
}}

canvas.addEventListener("mousemove", (event) => {{
  const now = Date.now();
  if (now - lastMove < 40) return;
  lastMove = now;
  mouse("mouseMoved", event);
}});
canvas.addEventListener("mousedown", (event) => {{ event.preventDefault(); mouse("mousePressed", event, event.detail); }});
canvas.addEventListener("mouseup", (event) => {{ event.preventDefault(); mouse("mouseReleased", event, event.detail); }});
canvas.addEventListener("contextmenu", (event) => event.preventDefault());
canvas.addEventListener("wheel", (event) => {{
  event.preventDefault();
  const at = place(event);
  send({{t: "mouse", type: "mouseWheel", x: at.x, y: at.y,
         deltaX: event.deltaX, deltaY: event.deltaY}});
}}, {{passive: false}});

screenEl.addEventListener("keydown", (event) => {{
  if (event.key === "F5" || event.key === "F12") return;
  event.preventDefault();
  const printable = event.key.length === 1;
  send({{t: "key", type: "keyDown", key: event.key, code: event.code,
         text: printable ? event.key : undefined,
         windowsVirtualKeyCode: event.keyCode, nativeVirtualKeyCode: event.keyCode,
         modifiers: modifiers(event)}});
}});
screenEl.addEventListener("keyup", (event) => {{
  event.preventDefault();
  send({{t: "key", type: "keyUp", key: event.key, code: event.code,
         windowsVirtualKeyCode: event.keyCode, modifiers: modifiers(event)}});
}});
// A pasted password is the normal way in, and it never becomes keystrokes.
screenEl.addEventListener("paste", (event) => {{
  const text = (event.clipboardData || window.clipboardData).getData("text");
  if (text) {{ event.preventDefault(); send({{t: "text", text: text}}); }}
}});
screenEl.addEventListener("mousedown", () => screenEl.focus());
screenEl.focus();

const STATE_TEXT = {{
  idle: "page_idle", starting: "page_waiting", waiting: "page_waiting",
  signed_in: "page_signed_in", captured: "page_captured",
}};
async function poll() {{
  try {{
    const response = await fetch("/login/state", {{cache: "no-store"}});
    const state = await response.json();
    if (state.state === "failed") {{
      done = true;
      statusEl.textContent = S.page_failed.replace("{{detail}}", state.detail || "?");
    }} else {{
      statusEl.textContent = S[STATE_TEXT[state.state] || "page_waiting"];
      if (state.state === "captured") done = true;
    }}
    finishEl.disabled = done || state.state === "idle";
    cancelEl.disabled = done || state.state === "idle";
  }} catch (error) {{
    statusEl.textContent = S.page_disconnected;
  }}
  if (!done) setTimeout(poll, 1500);
}}
finishEl.addEventListener("click", () => {{
  finishEl.disabled = true;
  fetch("/login/ready", {{method: "POST"}});
}});
cancelEl.addEventListener("click", () => {{
  cancelEl.disabled = true;
  fetch("/login/cancel", {{method: "POST"}});
}});

connect();
poll();
</script>
</body></html>"""


class LoginEndpoint:
    """Owns the viewer page, the token it is reached with, and the login browser."""

    def __init__(
        self, *, host: str, port: int, on_accepted: Callable[[int], None],
        enabled: Callable[[], bool], expected_user_id: Callable[[], int | None] = lambda: None,
        on_finished: Callable[[str, str | None], None] = lambda state, detail: None,
        clock: Callable[[], float] = time, session_file: Path = IMPORTED_SESSION_PATH,
    ):
        self.host: str = host
        self.port: int = port
        self.login: BrowserLogin | None = None
        self.on_accepted = on_accepted
        self.enabled = enabled
        self.expected_user_id = expected_user_id
        self.on_finished = on_finished
        self.clock = clock
        self._session_file = session_file
        self._token: str | None = None
        self._task: asyncio.Task | None = None
        self._runner: web.AppRunner | None = None
        self._sockets: set[web.WebSocketResponse] = set()

    # -- addresses ---------------------------------------------------------

    @property
    def bind_address(self) -> str:
        """What the socket is actually bound to - not necessarily connectable."""
        return f"http://{self.host}:{self.port}"

    @property
    def addresses(self) -> list[str]:
        """
        URLs to try, most likely first.

        Binding to a wildcard address is how a listener accepts connections on
        every interface, but it is not an address anything can dial. Which real
        address works depends on where the browser doing the signing in is, so
        more than one is offered whenever the host has more than one.
        """
        if self.host not in WILDCARD_HOSTS:
            return [f"http://{self.host}:{self.port}"]
        hosts = local_ipv4_addresses() or ["127.0.0.1"]
        return [f"http://{host}:{self.port}" for host in hosts]

    @property
    def loopback(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def urls(self) -> list[str]:
        """Where the user is told to go, token and all. Empty when idle."""
        if self._token is None:
            return []
        return [f"{address}/login/{self._token}" for address in self.addresses]

    @property
    def loopback_url(self) -> str | None:
        """The same page for someone sitting at the miner themselves."""
        if self._token is None:
            return None
        return f"{self.loopback}/login/{self._token}"

    @property
    def listening(self) -> bool:
        return self._runner is not None

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> None:
        """Bind the endpoint. Raises OSError when the port is unavailable."""
        if self._runner is not None:
            return
        app = web.Application(client_max_size=MAX_INPUT_BYTES)
        app.add_routes([
            web.get("/login", self._page),
            web.get("/login/ws", self._socket),
            web.get("/login/state", self._state),
            web.post("/login/ready", self._ready),
            web.post("/login/cancel", self._cancel),
            # Last: a dynamic segment matches anything, so every fixed path
            # under /login has to be registered before it.
            web.get("/login/{token}", self._enter),
        ])
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            await web.TCPSite(runner, self.host, self.port).start()
        except BaseException:
            await runner.cleanup()
            raise
        self._runner = runner

    async def stop(self) -> None:
        """Release the socket and abandon any sign-in in progress."""
        runner, self._runner = self._runner, None
        self._token = None
        await self.stop_login()
        # Before the runner, deliberately: cleaning it up waits for every
        # handler to return, and a viewer's page holds its websocket open
        # indefinitely - so quitting the miner would sit there for as long as
        # someone had the page open in a tab.
        for socket_ in list(self._sockets):
            with suppress(Exception):
                await socket_.close()
        self._sockets.clear()
        if runner is not None:
            with suppress(Exception):
                await runner.cleanup()

    async def begin(self, executable: str) -> None:
        """
        Open a browser and start waiting for the user to sign in.

        Each attempt gets a fresh token, so a page left open from a previous
        one cannot be used to drive this one.
        """
        await self.stop_login()
        self._token = secrets.token_urlsafe(32)
        self.login = BrowserLogin(
            executable=executable, on_accepted=self.on_accepted,
            expected_user_id=self.expected_user_id, clock=self.clock,
            session_file=self._session_file,
        )
        self._task = asyncio.create_task(self._run())

    async def stop_login(self) -> None:
        """
        Abandon a sign-in in progress.

        The event is set as well as the task cancelled: the event is what a user
        pressing Cancel means, and the cancellation is what a shutdown needs -
        waiting for the poll to notice would hold closing the miner up for it.
        """
        task, self._task = self._task, None
        if self.login is not None:
            self.login.cancel()
        if task is not None and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await asyncio.gather(task, return_exceptions=True)

    async def _run(self) -> None:
        login = self.login
        if login is None:
            return
        ended = True
        try:
            await login.run()
        except asyncio.CancelledError:
            # Being shut down is not an attempt that failed, and saying so would
            # put a failure in the log every time the miner stops mid-sign-in.
            ended = False
            raise
        except SessionImportError as error:
            logger.info(f"The browser sign-in did not complete ({error.code})")
        except Exception:
            logger.exception("The browser sign-in failed")
        finally:
            # Whoever asked for this is waiting on a session, not on a task, so
            # an attempt that ended any other way has to be reported.
            if ended and login.state != "captured":
                self.on_finished(login.state, login.detail)

    def status(self) -> dict[str, Any]:
        if self.login is None:
            return {"state": "idle", "detail": None, "watching": 0}
        return self.login.status()

    # -- guarding ----------------------------------------------------------

    @staticmethod
    def _same_origin(request: web.Request, origin: str) -> bool:
        try:
            parsed = URL(origin)
        except ValueError:
            return False
        if parsed.host is None:
            return False
        # A cookie is not scoped to a port, so the port has to be compared here
        # rather than assumed from the host.
        return (
            parsed.host == request.url.host
            and _port(parsed) == _port(request.url)
        )

    def _authorize(self, request: web.Request) -> None:
        """
        Only the page that was handed the token may drive the browser.

        A cross-origin page cannot read the cookie it is checked against, and
        browsers always attach Origin to the requests one makes - so requiring
        the cookie and refusing a foreign Origin keeps out both a page the user
        was tricked into visiting and anything else on the network that guessed.
        """
        if not self.enabled():
            raise _Rejected(403, "disabled")
        if self._token is None:
            raise _Rejected(403, "idle")
        origin = request.headers.get("Origin")
        if origin is not None and not self._same_origin(request, origin):
            raise _Rejected(403, "origin")
        if not self._matches(request.cookies.get(COOKIE_NAME, "")):
            raise _Rejected(401, "token")

    def _matches(self, candidate: str) -> bool:
        """
        Whether a value presented is the token, in constant time.

        Compared as bytes: `compare_digest` refuses non-ASCII text, and both a
        cookie and a path segment can carry whatever a client chose to send -
        which has to be a rejection rather than an error.
        """
        if self._token is None:
            return False
        return secrets.compare_digest(
            candidate.encode("utf-8", "surrogateescape"), self._token.encode("ascii")
        )

    @staticmethod
    def _reject(rejected: _Rejected) -> web.Response:
        return web.json_response({"detail": rejected.detail}, status=rejected.status)

    # -- endpoints ---------------------------------------------------------

    async def _enter(self, request: web.Request) -> web.Response:
        """The URL that was printed: trade the token for a cookie, then go."""
        token = request.match_info.get("token", "")
        if self._token is None or not self.enabled() or not self._matches(token):
            return self._reject(_Rejected(401, "token"))
        response = web.HTTPFound("/login")
        # Not `secure`: this is plain HTTP on a LAN, and a Secure cookie would
        # simply never be stored. httpOnly keeps it away from the page's script.
        response.set_cookie(
            COOKIE_NAME, self._token, httponly=True, samesite="Strict", path="/",
        )
        return response

    async def _page(self, request: web.Request) -> web.Response:
        try:
            self._authorize(request)
        except _Rejected as rejected:
            return self._reject(rejected)
        strings = {key: _("cli", "signin", key) for key in (
            "page_title", "page_idle", "page_waiting", "page_starting",
            "page_signed_in", "page_captured", "page_failed", "page_finish",
            "page_cancel", "page_hint", "page_disconnected",
        )}
        return web.Response(text=_page(strings), content_type="text/html")

    async def _state(self, request: web.Request) -> web.Response:
        try:
            self._authorize(request)
        except _Rejected as rejected:
            return self._reject(rejected)
        return web.json_response(self.status())

    async def _ready(self, request: web.Request) -> web.Response:
        """The user says the sign-in is done; stop waiting for more evidence."""
        try:
            self._authorize(request)
        except _Rejected as rejected:
            return self._reject(rejected)
        if self.login is not None:
            self.login.mark_ready()
        return web.json_response({"ok": True})

    async def _cancel(self, request: web.Request) -> web.Response:
        try:
            self._authorize(request)
        except _Rejected as rejected:
            return self._reject(rejected)
        if self.login is not None:
            self.login.cancel()
        return web.json_response({"ok": True})

    async def _socket(self, request: web.Request) -> web.StreamResponse:
        try:
            self._authorize(request)
        except _Rejected as rejected:
            return self._reject(rejected)
        login = self.login
        if login is None:
            return self._reject(_Rejected(403, "idle"))

        socket_ = web.WebSocketResponse(heartbeat=30, max_msg_size=MAX_INPUT_BYTES)
        await socket_.prepare(request)
        self._sockets.add(socket_)
        frames = login.subscribe()
        pump = asyncio.create_task(self._pump(socket_, frames))
        try:
            async for message in socket_:
                if message.type != aiohttp.WSMsgType.TEXT:
                    break
                try:
                    data = json.loads(message.data)
                except (ValueError, UnicodeError, RecursionError):
                    continue
                if isinstance(data, dict):
                    await login.input(data)
        finally:
            pump.cancel()
            await asyncio.gather(pump, return_exceptions=True)
            login.unsubscribe(frames)
            self._sockets.discard(socket_)
        return socket_

    @staticmethod
    async def _pump(socket_: web.WebSocketResponse, frames: asyncio.Queue) -> None:
        """Forward frames for as long as the viewer is there to take them."""
        while True:
            frame = await frames.get()
            try:
                await socket_.send_json(frame)
            except (ConnectionResetError, RuntimeError, aiohttp.ClientError):
                return
