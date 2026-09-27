"""
Server side of the desktop login helper protocol.

The helper (a separate program, run on a machine with a real browser) signs into
Twitch, captures the resulting web request context and uploads it here. See
`session_import` for what is in it.

The protocol is fixed by the helper, which validates every response strictly:

    POST /api/helper/connect                -> {"version", "connection", "expires_at"}
    POST /api/helper/session  <seed>        -> accepted payload
    GET  /api/helper/result                 -> {"state": "pending"} | accepted payload

Because the accept endpoint installs credentials, it is only opened when the
user enables it, and it only answers requests that no plain web page could have
produced.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import re
import secrets
import socket
from contextlib import suppress
from pathlib import Path
from time import time
from typing import Any, Callable

import aiohttp
from aiohttp import web

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

# Error details the helper understands; anything else becomes a generic rejection
# on its side, which is what we want for diagnostics we keep to ourselves.
DETAIL_DISABLED = "session_helper_disabled"
DETAIL_EXPIRED = "session_helper_expired"
DETAIL_INVALID = "session_helper_connection_invalid"
DETAIL_REJECTED = "session_helper_rejected"

WILDCARD_HOSTS = frozenset({"", "0.0.0.0", "::", "[::]"})


def primary_ipv4() -> str | None:
    """
    The address the routing table would use for outbound traffic.

    Connecting a UDP socket sends nothing; it only asks which local address
    would be used. On a single-homed host this is the right answer.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.0.2.1", 9))  # TEST-NET-1, reserved and unroutable
            address = sock.getsockname()[0]
    except OSError:
        return None
    return address or None


def _linux_interfaces() -> list[str]:
    """
    Every address assigned to a local interface, in interface order.

    Resolving the hostname usually yields only one of them, which is not enough
    on a host with several - a LAN address, a VPN, container bridges. The kernel
    lists them all here, each address line followed by its route type.
    """
    try:
        with open("/proc/net/fib_trie", encoding="ascii", errors="replace") as handle:
            lines = handle.read().splitlines()
    except OSError:
        return []
    found: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(r"\s*\|--\s+(\d+\.\d+\.\d+\.\d+)\s*$", line)
        if match is None:
            continue
        following = lines[index + 1] if index + 1 < len(lines) else ""
        # "host LOCAL" marks an address of this machine, as opposed to a route.
        if "host LOCAL" in following and match.group(1) not in found:
            found.append(match.group(1))
    return found


def local_ipv4_addresses() -> list[str]:
    """
    Every IPv4 address this host might be reachable at, most likely first.

    A machine can have several - LAN, VPN, a container bridge - and which of
    them the helper can reach depends on where the helper runs, which this
    process cannot know. So they are all offered, rather than one presented as
    fact. Loopback is left out; the caller offers it separately.
    """
    found: list[str] = []
    primary = primary_ipv4()
    if primary is not None and not primary.startswith("127."):
        found.append(primary)
    for address in _linux_interfaces():
        if not address.startswith("127.") and address not in found:
            found.append(address)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            address = info[4][0]
            if not address.startswith("127.") and address not in found:
                found.append(address)
    except OSError:
        pass
    return found


class HelperServer:
    """Owns the helper HTTP endpoints and the tickets they are reached with."""

    CONNECTION_SECONDS = 600
    # The helper rejects a ticket that lives longer than 660 seconds.
    MAX_CONNECTIONS = 8
    MAX_RECEIPTS = 8

    def __init__(
        self,
        *,
        host: str,
        port: int,
        on_accepted: Callable[[int], None],
        enabled: Callable[[], bool],
        expected_user_id: Callable[[], int | None] = lambda: None,
        session_file: Path = IMPORTED_SESSION_PATH,
    ):
        self.host: str = host
        self.port: int = port
        self.on_accepted = on_accepted
        self.enabled = enabled
        self.expected_user_id = expected_user_id
        self._file = PrivateSessionFile(session_file)
        self._connections: dict[str, tuple[float, int]] = {}
        self._receipts: dict[str, dict[str, Any]] = {}
        self._generation: int = 0
        self._lock: asyncio.Lock = asyncio.Lock()
        # Probes never touch the miner's cookie jar: the captured context is the
        # only identity we may present.
        self._probe: aiohttp.ClientSession | None = None
        self._runner: web.AppRunner | None = None
        self._site: web.TCPSite | None = None

    # -- lifecycle ---------------------------------------------------------

    @property
    def bind_address(self) -> str:
        """What the socket is actually bound to - not necessarily connectable."""
        return f"http://{self.host}:{self.port}"

    @property
    def addresses(self) -> list[str]:
        """
        URLs to try, most likely first.

        Binding to a wildcard address is how a listener accepts connections on
        every interface, but it is not an address anything can dial - the helper
        gets a network error if it is handed one. Which real address works
        depends on the helper's own network position, so more than one is
        offered whenever the host has more than one.
        """
        if self.host not in WILDCARD_HOSTS:
            return [f"http://{self.host}:{self.port}"]
        hosts = local_ipv4_addresses() or ["127.0.0.1"]
        return [f"http://{host}:{self.port}" for host in hosts]

    @property
    def loopback(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def address(self) -> str:
        """The first address to try. Use `addresses` when presenting choices."""
        return self.addresses[0]

    async def start(self) -> None:
        """Bind the endpoints. Raises OSError when the port is unavailable."""
        if self._runner is not None:
            return
        app = web.Application(client_max_size=SessionBundle.MAX_BYTES)
        app.add_routes([
            web.post("/api/helper/connect", self._connect),
            web.post("/api/helper/session", self._session),
            web.get("/api/helper/result", self._result),
        ])
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        try:
            site = web.TCPSite(runner, self.host, self.port)
            await site.start()
        except BaseException:
            await runner.cleanup()
            raise
        self._runner, self._site = runner, site

    async def stop(self) -> None:
        """Release the listening socket. Cancelling a task would not."""
        runner, self._runner, self._site = self._runner, None, None
        self._connections.clear()
        self._receipts.clear()
        if runner is not None:
            with suppress(Exception):
                await runner.cleanup()
        if self._probe is not None:
            with suppress(Exception):
                await self._probe.close()
            self._probe = None

    # -- request plumbing --------------------------------------------------

    @staticmethod
    def _reject(status: int, detail: str) -> web.Response:
        return web.json_response({"detail": detail}, status=status)

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode()).hexdigest()

    def _check(self, token: str) -> None:
        """Validate a bearer ticket, raising a response-shaped error on failure."""
        if not self.enabled():
            raise _Rejected(403, DETAIL_DISABLED)
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise _Rejected(401, DETAIL_INVALID)
        entry = self._connections.get(self._digest(token))
        if entry is None:
            raise _Rejected(401, DETAIL_INVALID)
        if entry[0] <= time():
            raise _Rejected(401, DETAIL_EXPIRED)

    def _guard(self, request: web.Request) -> None:
        """
        Only the helper gets to talk to these endpoints.

        A browser cannot set X-TDM-Request on a cross-origin request without a
        preflight, and it always attaches Origin to one - so requiring the first
        and refusing the second keeps web pages (and anything a user is tricked
        into visiting) out.
        """
        if request.headers.get("X-TDM-Request") != "1":
            raise _Rejected(403, DETAIL_REJECTED)
        if request.headers.get("Origin") is not None:
            raise _Rejected(403, DETAIL_REJECTED)

    async def _body(self, request: web.Request) -> Any:
        raw = await request.content.read(SessionBundle.MAX_BYTES + 1)
        if len(raw) > SessionBundle.MAX_BYTES:
            raise _Rejected(400, DETAIL_REJECTED)
        try:
            return json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            raise _Rejected(400, DETAIL_REJECTED) from None

    @staticmethod
    def _bearer(request: web.Request) -> str:
        header = request.headers.get("Authorization", "")
        if not header.startswith("Bearer "):
            raise _Rejected(401, DETAIL_INVALID)
        return header[7:]

    # -- endpoints ---------------------------------------------------------

    async def _connect(self, request: web.Request) -> web.Response:
        try:
            self._guard(request)
            await self._body(request)
            if not self.enabled():
                raise _Rejected(403, DETAIL_DISABLED)
            async with self._lock:
                now = time()
                self._connections = {
                    key: value for key, value in self._connections.items() if value[0] > now
                }
                if len(self._connections) >= self.MAX_CONNECTIONS:
                    raise _Rejected(429, DETAIL_REJECTED)
                token = secrets.token_urlsafe(32)
                expiry = now + self.CONNECTION_SECONDS
                self._connections[self._digest(token)] = (expiry, self._generation)
            return web.json_response({"version": 1, "connection": token, "expires_at": expiry})
        except _Rejected as rejected:
            return self._reject(rejected.status, rejected.detail)

    async def _result(self, request: web.Request) -> web.Response:
        try:
            self._guard(request)
            token = self._bearer(request)
            # The receipt is checked before the ticket: a lost acknowledgement
            # makes the helper ask again, and it must get the same answer even
            # though the ticket has already been used.
            receipt = self._receipts.get(self._digest(token))
            if receipt is not None:
                return web.json_response(receipt)
            self._check(token)
            return web.json_response({"state": "pending"})
        except _Rejected as rejected:
            return self._reject(rejected.status, rejected.detail)

    async def _session(self, request: web.Request) -> web.Response:
        try:
            self._guard(request)
            token = self._bearer(request)
            payload = await self._body(request)
            self._check(token)
            seed = self._unpack(payload)
            user_id = await self._probe_bundle(seed.bundle)
            expected = self.expected_user_id()
            if expected is not None and expected != user_id:
                # Switching accounts mid-run would leave the user id baked into
                # websocket topics and cached payloads pointing at the old one.
                raise SessionImportError("ACCOUNT_MISMATCH")
            async with self._lock:
                self._check(token)
                seed.bundle.require_fresh()
                self._file.write(seed)
                self._generation += 1
                digest = self._digest(token)
                accepted = {
                    "success": True,
                    # The flag exists for the original dashboard; always off.
                    "allow_helper_connection": False,
                    "session": {
                        "state": "ready",
                        "user_id": user_id,
                        "generation": self._generation,
                        "expires_at": seed.bundle.expires_at,
                    },
                }
                self._receipts[digest] = accepted
                while len(self._receipts) > self.MAX_RECEIPTS:
                    self._receipts.pop(next(iter(self._receipts)))
                # Tickets stay valid so the helper can still read the receipt.
            logger.info(f"Imported a browser session for user ID {user_id}")
            self.on_accepted(user_id)
            return web.json_response(accepted)
        except _Rejected as rejected:
            return self._reject(rejected.status, rejected.detail)
        except SessionImportError as error:
            logger.warning(f"Rejected an imported session: {error.code}")
            return self._reject(400, DETAIL_REJECTED)
        except Exception:
            logger.exception("Failed to accept an imported session")
            return self._reject(500, DETAIL_REJECTED)

    # -- validation --------------------------------------------------------

    @staticmethod
    def _unpack(payload: Any) -> ServerSeed:
        """
        Pull the seed out of the payload the helper sends.

        The context itself is validated strictly - it is what the miner will run
        on. The SDK cookie only feeds renewal, so a stale or unreadable one costs
        the ability to renew rather than the whole login.
        """
        if not isinstance(payload, dict) or set(payload) != {"version", "bundle", "sdk_cookie"}:
            raise SessionImportError("FORMAT")
        if type(payload["version"]) is not int or payload["version"] != 1:
            raise SessionImportError("FORMAT")
        bundle = SessionBundle.from_dict(payload["bundle"])
        bundle.require_fresh()
        cookie = None
        raw_cookie = payload["sdk_cookie"]
        if raw_cookie is not None:
            try:
                cookie = SDKCookie.from_dict(raw_cookie)
                cookie.require_fresh(time())
            except SessionImportError as error:
                cookie = None
                logger.warning(
                    f"The uploaded session cannot be renewed ({error.code}) - it will"
                    f" stop working when it expires"
                )
        return ServerSeed(bundle, cookie)

    async def _get_probe(self) -> aiohttp.ClientSession:
        if self._probe is None or self._probe.closed:
            self._probe = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                cookie_jar=aiohttp.DummyCookieJar(),
                headers={"Accept": "*/*", "Accept-Encoding": "gzip"},
            )
        return self._probe

    async def _probe_bundle(self, bundle: SessionBundle) -> int:
        """Prove the captured context works before storing it."""
        return await probe_bundle(bundle, await self._get_probe())


class _Rejected(Exception):
    """Internal carrier for a prepared error response."""

    def __init__(self, status: int, detail: str):
        self.status: int = status
        self.detail: str = detail
        super().__init__(detail)
