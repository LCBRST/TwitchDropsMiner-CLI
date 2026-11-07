"""
HTTP management API and web dashboard host for the CLI miner.

The server shares the miner's asyncio loop, exactly like the sign-in endpoint
in ``login_server.py``. It binds every interface by default so the dashboard
works from a phone or another computer on the LAN; every ``/api`` request needs
the management token, which is generated when the API is first enabled and can
be shown with the ``api token`` command. Set ``api_host`` to ``127.0.0.1`` to
keep it on this machine.

The dashboard itself is static files under ``webui/``. Their source lives in
the TwitchDropMiner_WebAddon repository; ``scripts/sync-webui.sh`` copies a
checkout into this tree and the PyInstaller spec bundles it into the binary.
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import re
import secrets
from contextlib import suppress
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import aiohttp
from aiohttp import web
from yarl import URL

from twitchdropsminer.common.constants import PriorityMode, State, _resource_path
from twitchdropsminer.web.image_cache import IMAGE_NAME, ImageCache
from twitchdropsminer.auth.login_server import start_reason
from twitchdropsminer.common.utils import WILDCARD_HOSTS, local_ipv4_addresses
from twitchdropsminer.common.version import __version__

if TYPE_CHECKING:
    from twitchdropsminer.core.channel import Channel
    from twitchdropsminer.core.inventory import DropsCampaign, TimedDrop
    from twitchdropsminer.core.twitch import Twitch


logger = logging.getLogger("TwitchDrops")

MAX_BODY_BYTES = 64 * 1024
EVENT_INTERVAL = 2.0
HOP_BY_HOP = frozenset({
    "connection", "keep-alive", "proxy-authenticate", "proxy-authorization",
    "te", "trailers", "transfer-encoding", "upgrade",
})
ASSET_NAME = re.compile(r"[A-Za-z0-9._-]+")
MODE_NAMES = {
    "priority_only": PriorityMode.PRIORITY_ONLY,
    "ending_soonest": PriorityMode.ENDING_SOONEST,
    "low_avbl_first": PriorityMode.LOW_AVBL_FIRST,
}


# ---------------------------------------------------------------------------
# JSON serialization
# ---------------------------------------------------------------------------


def _game_data(game: Any) -> dict[str, Any] | None:
    if game is None:
        return None
    return {"id": game.id, "name": game.name, "slug": game.slug}


def _channel_brief(channel: Channel | None) -> dict[str, Any] | None:
    if channel is None:
        return None
    return {
        "id": channel.id,
        "login": channel._login,
        "name": channel.name,
        "game": _game_data(channel.game),
    }


def _channel_data(twitch: Twitch, channel: Channel) -> dict[str, Any]:
    watching = twitch.watching_channel.get_with_default(None)
    # The TUI's selection is consumed by the state machine when it switches,
    # so peek instead of calling get_selection().
    selection = getattr(twitch.gui.channels, "_selection", None)
    return {
        **_channel_brief(channel),
        "online": channel.online,
        "pending_online": channel.pending_online,
        "acl_based": channel.acl_based,
        "drops_enabled": channel.drops_enabled,
        "viewers": channel.viewers,
        "watching": watching is not None and watching.id == channel.id,
        "selected": selection is not None and selection.id == channel.id,
        "can_watch": twitch.can_watch(channel),
    }


def _drop_data(drop: TimedDrop, images: ImageCache | None = None) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    return {
        "id": drop.id,
        "name": drop.name,
        "rewards": drop.rewards_text(),
        "benefits": [
            {
                "id": benefit.id,
                "name": benefit.name,
                "type": benefit.type.value,
                "image_url": str(benefit.image_url),
                "cached_image_url": (
                    images.url_for(str(benefit.image_url)) if images is not None else None
                ),
            }
            for benefit in drop.benefits
        ],
        "required_minutes": drop.required_minutes,
        "current_minutes": drop.current_minutes,
        "remaining_minutes": max(drop.remaining_minutes, 0),
        "progress": round(drop.progress, 4),
        "claimed": drop.is_claimed,
        "claimable": drop.can_claim,
        "can_earn": drop.can_earn(),
        "preconditions_met": drop.preconditions_met,
        "precondition_drops": list(drop.precondition_drops),
        "active": drop.starts_at <= now < drop.ends_at,
        "starts_at": drop.starts_at.isoformat(),
        "ends_at": drop.ends_at.isoformat(),
    }


def _campaign_data(
    campaign: DropsCampaign, images: ImageCache | None = None
) -> dict[str, Any]:
    image_url = str(campaign.image_url)
    return {
        "id": campaign.id,
        "name": campaign.name,
        "game": _game_data(campaign.game),
        "image_url": image_url,
        "cached_image_url": (
            images.url_for(image_url) if images is not None else None
        ),
        "linked": campaign.linked,
        "eligible": campaign.eligible,
        "active": campaign.active,
        "upcoming": campaign.upcoming,
        "expired": campaign.expired,
        "finished": campaign.finished,
        "claimed_drops": campaign.claimed_drops,
        "total_drops": campaign.total_drops,
        "required_minutes": campaign.required_minutes,
        "remaining_minutes": campaign.remaining_minutes,
        "progress": round(campaign.progress, 4),
        "availability": (
            round(campaign.availability, 2) if math.isfinite(campaign.availability) else None
        ),
        "starts_at": campaign.starts_at.isoformat(),
        "ends_at": campaign.ends_at.isoformat(),
        "allowed_channels": [_channel_brief(ch) for ch in campaign.allowed_channels],
        "drops": [_drop_data(drop, images) for drop in campaign.drops],
    }


def _progress_data(drop: TimedDrop | None) -> dict[str, Any] | None:
    if drop is None:
        return None
    campaign = drop.campaign
    return {
        "drop": {
            "id": drop.id,
            "name": drop.name,
            "current_minutes": drop.current_minutes,
            "required_minutes": drop.required_minutes,
            "progress": round(drop.progress, 4),
            "rewards": drop.rewards_text(),
        },
        "campaign": {
            "id": campaign.id,
            "name": campaign.name,
            "game": campaign.game.name,
            "claimed_drops": campaign.claimed_drops,
            "total_drops": campaign.total_drops,
            "progress": round(campaign.progress, 4),
        },
    }


def _status_data(twitch: Twitch) -> dict[str, Any]:
    watching = twitch.watching_channel.get_with_default(None)
    started = getattr(twitch.gui, "_start_time", None)
    uptime = int((datetime.now() - started).total_seconds()) if started else 0
    login = twitch.gui.login
    return {
        "version": __version__,
        "language": twitch.settings.language,
        "state": twitch._state.name,
        "watching": _channel_brief(watching),
        "progress": _progress_data(twitch.gui.progress.current),
        "counts": {
            "campaigns": len(twitch.inventory),
            "active_campaigns": sum(
                1 for campaign in twitch.inventory if campaign.active
            ),
            "claimed_drops": sum(
                campaign.claimed_drops for campaign in twitch.inventory
            ),
            "claimable_drops": sum(
                1
                for campaign in twitch.inventory
                for drop in campaign.drops
                if drop.can_claim
            ),
            "channels": len(twitch.channels),
            "wanted_games": len(twitch.wanted_games),
            "websockets": len(twitch.gui.websockets.entries),
        },
        "wanted_games": [game.name for game in twitch.wanted_games],
        "priority": list(twitch.settings.priority),
        "login": {"status": login.status, "user_id": login.user_id},
        "websockets": [
            {"idx": entry.idx, "status": entry.status, "topics": entry.topics}
            for entry in twitch.gui.websockets.entries
        ],
        "uptime_seconds": uptime,
        "time": datetime.now(timezone.utc).isoformat(),
    }


def _settings_data(settings: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in settings._settings.items():
        if key == "api_token":
            result[key] = {"configured": bool(value)}
            continue
        result[key] = _plain_value(value)
    return result


def _plain_value(value: Any) -> Any:
    if isinstance(value, URL):
        return str(value)
    if isinstance(value, set):
        return sorted(value)
    if isinstance(value, PriorityMode):
        return value.name.lower()
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _login_data(twitch: Twitch) -> dict[str, Any]:
    info = twitch.login_status()
    # These carry a one-off sign-in token, but this endpoint itself requires the
    # management token - the dashboard is already an authenticated operator.
    # Keep them so a headless miner can be signed in from the web page.
    info["user_id"] = twitch.gui.login.user_id
    info["status_text"] = twitch.gui.login.status
    return info


def _error(message: str, status: int = 400) -> web.Response:
    return web.json_response({"error": message}, status=status)


# ---------------------------------------------------------------------------
# Settings coercion
# ---------------------------------------------------------------------------

BOOL_KEYS = {
    "enable_badges_emotes", "available_drops_check", "login_server_enabled",
}
INT_KEYS = {
    "connection_quality": (0, 2),
    "reload_interval": (10, 1440),
    "login_server_port": (1, 65535),
}
STRING_KEYS = {"language", "login_server_host", "renewal_browser_path"}
# api_* is deliberately not writable here: changing the listener from one of
# its own requests would tear the connection down mid-response. Use the CLI.
READONLY_KEYS = {
    "api_enabled", "api_host", "api_port", "api_token", "api_auth_enabled",
}


def _coerce_setting(key: str, value: Any) -> Any:
    if key in BOOL_KEYS:
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, str)):
            text = str(value).strip().lower()
            if text in ("1", "true", "yes", "on"):
                return True
            if text in ("0", "false", "no", "off", ""):
                return False
        raise ValueError("expected a boolean")
    if key in INT_KEYS:
        low, high = INT_KEYS[key]
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise ValueError("expected an integer") from None
        if not low <= number <= high:
            raise ValueError(f"expected {low}..{high}")
        return number
    if key == "proxy":
        return URL(str(value or ""))
    if key == "exclude":
        if isinstance(value, str):
            value = [part.strip() for part in value.split(",") if part.strip()]
        if not isinstance(value, list) or not all(isinstance(part, str) for part in value):
            raise ValueError("expected a list of game names")
        return set(value)
    if key == "priority":
        if isinstance(value, str):
            value = [part.strip() for part in value.split(",") if part.strip()]
        if not isinstance(value, list) or not all(isinstance(part, str) for part in value):
            raise ValueError("expected a list of game names")
        return value
    if key == "priority_mode":
        if isinstance(value, int) and not isinstance(value, bool):
            try:
                return PriorityMode(value)
            except ValueError:
                raise ValueError("expected priority_only, ending_soonest or low_avbl_first") from None
        name = str(value).strip().lower()
        if name not in MODE_NAMES:
            raise ValueError("expected priority_only, ending_soonest or low_avbl_first")
        return MODE_NAMES[name]
    if key in STRING_KEYS:
        if not isinstance(value, str):
            raise ValueError("expected a string")
        return value
    raise ValueError("unknown setting")


# ---------------------------------------------------------------------------
# Endpoint
# ---------------------------------------------------------------------------


class APIEndpoint:
    """The management API server, owned by a Twitch instance."""

    def __init__(self, twitch: Twitch) -> None:
        self._twitch = twitch
        self.host: str = twitch.settings.api_host
        self.port: int = int(twitch.settings.api_port)
        self._runner: web.AppRunner | None = None
        self._started: bool = False
        self.error: str | None = None
        # Long-lived SSE responses must be told to stop before runner.cleanup()
        # waits on them, or a shutdown with a dashboard open would hang.
        self._stop_event = asyncio.Event()
        self._streams: set[web.StreamResponse] = set()
        # The sign-in page and its websocket are proxied through this server so
        # the dashboard can embed it without a second forwarded port.
        self._proxy_session: aiohttp.ClientSession | None = None
        # Reward and campaign artwork, cached under the data directory and
        # swept when campaigns disappear from the inventory.
        self._images: ImageCache | None = None
        self._cache_task: asyncio.Task | None = None

    # -- addresses ---------------------------------------------------------

    @property
    def listening(self) -> bool:
        return self._started

    @property
    def bind_address(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def addresses(self) -> list[str]:
        """URLs to try, loopback first when the bind is a wildcard."""
        if self.host not in WILDCARD_HOSTS:
            host = f"[{self.host}]" if ":" in self.host else self.host
            return [f"http://{host}:{self.port}/"]
        hosts = local_ipv4_addresses() or ["127.0.0.1"]
        if "127.0.0.1" not in hosts:
            hosts = ["127.0.0.1", *hosts]
        return [f"http://{host}:{self.port}/" for host in hosts]

    @property
    def url(self) -> str:
        """The address to open on the miner itself."""
        return self.addresses[0]

    @property
    def urls(self) -> list[str]:
        """Every address the dashboard can be opened at."""
        return self.addresses

    # -- lifecycle ---------------------------------------------------------

    async def start(self) -> bool:
        # aiohttp's decorator stamps an attribute on the function, which a
        # bound method cannot hold - wrap it in a plain coroutine first.
        async def auth(request: web.Request, handler: Any) -> web.StreamResponse:
            return await self._auth_middleware(request, handler)

        app = web.Application(
            client_max_size=MAX_BODY_BYTES,
            middlewares=[web.middleware(auth)],
        )
        app.router.add_get("/healthz", self._healthz)
        app.router.add_get("/auth", self._auth_info)
        app.router.add_get("/", self._index)
        app.router.add_get("/assets/{name}", self._asset)
        app.router.add_get("/images/{name}", self._image)
        # Same-origin sign-in viewer. The login server keeps its own one-off
        # token and cookie; only the transport moves to this port.
        app.router.add_get("/login/ws", self._login_ws_proxy)
        app.router.add_route("*", "/login", self._login_http_proxy)
        app.router.add_route("*", "/login/{tail:.*}", self._login_http_proxy)
        app.router.add_get("/api/status", self._status)
        app.router.add_get("/api/channels", self._channels)
        app.router.add_get("/api/campaigns", self._campaigns)
        app.router.add_get("/api/settings", self._get_settings)
        app.router.add_post("/api/settings", self._post_settings)
        app.router.add_get("/api/login", self._login)
        app.router.add_get("/api/logs", self._logs)
        app.router.add_get("/api/events", self._events)
        app.router.add_post("/api/channels/select", self._select_channel)
        app.router.add_post("/api/actions/{action}", self._action)

        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        try:
            await site.start()
        except OSError as exc:
            await runner.cleanup()
            self.error = str(exc)
            logger.warning(f"Management API could not bind {self.bind_address}: {exc}")
            return False
        self._runner = runner
        self._started = True
        self.error = None
        self._stop_event.clear()
        self._proxy_session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=30),
            cookie_jar=aiohttp.DummyCookieJar(),
        )
        self._images = ImageCache(self._twitch)
        self._cache_task = asyncio.create_task(
            self._images.run(), name="api-image-cache"
        )
        logger.info(f"Management API listening at {self.url}")
        return True

    async def stop(self) -> None:
        self._started = False
        self._stop_event.set()
        # Let the SSE handlers leave their loops before cleanup waits on them.
        for _ in range(100):
            if not self._streams:
                break
            await asyncio.sleep(0.05)
        for response in list(self._streams):
            with suppress(Exception):
                await response.write_eof()
        self._streams.clear()
        runner, self._runner = self._runner, None
        if runner is not None:
            await runner.cleanup()
        if self._cache_task is not None:
            self._cache_task.cancel()
            self._cache_task = None
        self._images = None
        session, self._proxy_session = self._proxy_session, None
        if session is not None:
            await session.close()

    # -- auth --------------------------------------------------------------

    async def _auth_middleware(
        self, request: web.Request, handler: Any
    ) -> web.StreamResponse:
        if not request.path.startswith("/api/"):
            return await handler(request)
        if not self._twitch.settings.api_auth_enabled:
            return await handler(request)
        supplied = request.headers.get("X-API-Token", "")
        if not supplied:
            authorization = request.headers.get("Authorization", "")
            if authorization.startswith("Bearer "):
                supplied = authorization[7:]
        expected = self._twitch.settings.api_token
        if (
            not expected
            or not secrets.compare_digest(supplied.encode("utf8"), expected.encode("utf8"))
        ):
            return _error("unauthorized", 401)
        return await handler(request)

    # -- static dashboard --------------------------------------------------

    @property
    def _webui(self) -> Path:
        return _resource_path("webui")

    async def _healthz(self, request: web.Request) -> web.Response:
        return web.json_response({"ok": True})

    async def _auth_info(self, request: web.Request) -> web.Response:
        """Public: tells the dashboard whether it needs to ask for a token."""
        return web.json_response(
            {"required": bool(self._twitch.settings.api_auth_enabled)}
        )

    async def _index(self, request: web.Request) -> web.StreamResponse:
        path = self._webui / "index.html"
        if not path.is_file():
            return web.Response(
                text="The web dashboard files are missing from this build.",
                status=503,
                content_type="text/plain",
            )
        return web.FileResponse(path, headers={"Cache-Control": "no-cache"})

    async def _asset(self, request: web.Request) -> web.StreamResponse:
        name = request.match_info.get("name", "")
        if not ASSET_NAME.fullmatch(name):
            raise web.HTTPNotFound()
        path = self._webui / "assets" / name
        if not path.is_file():
            raise web.HTTPNotFound()
        return web.FileResponse(path, headers={"Cache-Control": "no-cache"})

    async def _image(self, request: web.Request) -> web.StreamResponse:
        """Serve reward/campaign artwork from the local cache."""
        name = request.match_info.get("name", "")
        if not IMAGE_NAME.fullmatch(name) or self._images is None:
            raise web.HTTPNotFound()
        path = await self._images.fetch(name)
        if path is None:
            raise web.HTTPNotFound()
        return web.FileResponse(
            path, headers={"Cache-Control": "public, max-age=86400"}
        )

    # -- sign-in page proxy ------------------------------------------------

    def _login_endpoint(self) -> Any | None:
        endpoint = self._twitch._login_endpoint
        if endpoint is None or not endpoint.listening:
            return None
        return endpoint

    @staticmethod
    def _public_host(request: web.Request) -> str:
        """
        The name the browser used, when a front end bothered to record it.

        A Cloudflare tunnel may pass its own host to the origin through the
        Host header (``httpHostHeader``), leaving only X-Forwarded-Host with
        the public name. If neither names the public host, the Host header is
        all there is.
        """
        forwarded = request.headers.get("X-Forwarded-Host", "")
        candidate = forwarded.split(",", 1)[0].strip() or request.host
        try:
            return URL(f"http://{candidate}").host or request.url.host
        except ValueError:
            return request.url.host

    @staticmethod
    def _same_origin_hint(request: web.Request, origin: URL) -> bool:
        """
        Whether this request really came from the page whose Origin it names.

        Compared against the host a browser cannot forge: the Origin header
        itself is what a cross-site page would lie in, but ``Sec-Fetch-Site``
        is set by the browser and is outside script control. A matching public
        host is the other witness, for browsers that do not send it.
        """
        if request.headers.get("Sec-Fetch-Site", "").lower() == "same-origin":
            return True
        return origin.host == APIEndpoint._public_host(request)

    def _proxy_headers(self, request: web.Request) -> dict[str, str]:
        headers: dict[str, str] = {}
        for key, value in request.headers.items():
            lower = key.lower()
            if (
                lower in HOP_BY_HOP
                or lower in ("host", "content-length")
                or lower.startswith("sec-websocket-")
            ):
                continue
            headers[key] = value
        # The sign-in endpoint checks Origin against the Host it sees, and its
        # cookie was issued for the dashboard's origin, so keep both as the
        # browser sent them.
        headers["Host"] = request.host
        # This hop is plain HTTP even when the browser reached the dashboard
        # over TLS, and the tunnel may also have rewritten Host or left a
        # wrong X-Forwarded-Proto behind. When the browser itself says the
        # request is same-origin, its Origin is the truth about the page it
        # came from, so present that host and scheme to the endpoint and the
        # check passes. A foreign Origin is forwarded untouched and still
        # rejected - and the token cookie is HttpOnly and SameSite=Strict, so
        # a foreign page cannot make an authorized request in the first place.
        origin = request.headers.get("Origin")
        if origin is not None:
            try:
                parsed = URL(origin)
            except ValueError:
                parsed = None
            if (
                parsed is not None
                and parsed.host is not None
                and parsed.scheme in ("http", "https")
                and self._same_origin_hint(request, parsed)
            ):
                authority = f"[{parsed.host}]" if ":" in parsed.host else parsed.host
                if parsed.explicit_port:
                    authority = f"{authority}:{parsed.explicit_port}"
                headers["Host"] = authority
                headers["X-Forwarded-Proto"] = parsed.scheme
                return headers
        if not any(key.lower() == "x-forwarded-proto" for key in headers):
            headers["X-Forwarded-Proto"] = request.scheme
        return headers

    async def _login_http_proxy(self, request: web.Request) -> web.Response:
        endpoint = self._login_endpoint()
        session = self._proxy_session
        if endpoint is None or session is None:
            return web.Response(status=503, text="the sign-in page is not running")
        target = f"http://127.0.0.1:{endpoint.port}{request.rel_url}"
        body = await request.read()
        try:
            async with session.request(
                request.method,
                target,
                headers=self._proxy_headers(request),
                data=body or None,
                allow_redirects=False,
            ) as upstream:
                payload = await upstream.read()
                response = web.Response(status=upstream.status, body=payload)
                for key, value in upstream.headers.items():
                    lower = key.lower()
                    if lower in HOP_BY_HOP or lower in (
                        "content-length", "content-encoding", "set-cookie",
                    ):
                        continue
                    response.headers[key] = value
                for cookie in upstream.headers.getall("Set-Cookie", []):
                    response.headers.add("Set-Cookie", cookie)
                return response
        except aiohttp.ClientError:
            return web.Response(status=502, text="the sign-in page is not responding")

    async def _login_ws_proxy(self, request: web.Request) -> web.StreamResponse:
        endpoint = self._login_endpoint()
        session = self._proxy_session
        if endpoint is None or session is None:
            return web.Response(status=503, text="the sign-in page is not running")
        target = f"http://127.0.0.1:{endpoint.port}/login/ws"
        try:
            upstream = await session.ws_connect(
                target, headers=self._proxy_headers(request), heartbeat=30,
            )
        except aiohttp.ClientError:
            return web.Response(status=502, text="the sign-in page is not responding")
        ws = web.WebSocketResponse(heartbeat=30)
        await ws.prepare(request)

        async def client_to_upstream() -> None:
            async for message in ws:
                if message.type == web.WSMsgType.TEXT:
                    await upstream.send_str(message.data)
                elif message.type == web.WSMsgType.BINARY:
                    await upstream.send_bytes(message.data)
                elif message.type in (
                    web.WSMsgType.CLOSE, web.WSMsgType.CLOSED, web.WSMsgType.ERROR,
                ):
                    break

        async def upstream_to_client() -> None:
            async for message in upstream:
                if message.type == aiohttp.WSMsgType.TEXT:
                    await ws.send_str(message.data)
                elif message.type == aiohttp.WSMsgType.BINARY:
                    await ws.send_bytes(message.data)
                elif message.type in (
                    aiohttp.WSMsgType.CLOSE, aiohttp.WSMsgType.CLOSED,
                    aiohttp.WSMsgType.ERROR,
                ):
                    break

        tasks = [
            asyncio.create_task(client_to_upstream()),
            asyncio.create_task(upstream_to_client()),
        ]
        try:
            await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        finally:
            for task in tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            await upstream.close()
            if not ws.closed:
                await ws.close()
        return ws

    # -- read endpoints ----------------------------------------------------

    async def _status(self, request: web.Request) -> web.Response:
        return web.json_response(_status_data(self._twitch))

    async def _channels(self, request: web.Request) -> web.Response:
        twitch = self._twitch
        return web.json_response(
            {"channels": [_channel_data(twitch, ch) for ch in twitch.channels.values()]}
        )

    async def _campaigns(self, request: web.Request) -> web.Response:
        if self._images is not None:
            # Register the current artwork and drop files whose campaigns are
            # no longer in the inventory (the campaign has ended).
            self._images.sync(self._twitch.inventory)
        campaigns = [
            _campaign_data(campaign, self._images)
            for campaign in self._twitch.inventory
        ]
        if self._images is not None:
            self._images.save()
        return web.json_response({"campaigns": campaigns})

    async def _get_settings(self, request: web.Request) -> web.Response:
        twitch = self._twitch
        return web.json_response(
            {
                "settings": _settings_data(twitch.settings),
                "api": {
                    "enabled": bool(twitch.settings.api_enabled),
                    "listening": self.listening,
                    "bind": self.bind_address,
                    "url": self.url,
                    "auth": bool(twitch.settings.api_auth_enabled),
                },
            }
        )

    async def _login(self, request: web.Request) -> web.Response:
        return web.json_response(_login_data(self._twitch))

    async def _logs(self, request: web.Request) -> web.Response:
        try:
            limit = int(request.query.get("limit", "200"))
        except ValueError:
            limit = 200
        limit = max(1, min(limit, 1000))
        lines = self._twitch.gui.output_buffer
        return web.json_response({"lines": lines[-limit:]})

    # -- write endpoints ---------------------------------------------------

    async def _post_settings(self, request: web.Request) -> web.Response:
        data, error = await self._json_object(request)
        if error is not None:
            return error
        settings = self._twitch.settings
        changed: list[str] = []
        for key, value in data.items():
            if key in READONLY_KEYS:
                return _error(f"{key} can only be changed from the CLI", 403)
            if key not in settings._settings:
                return _error(f"unknown setting: {key}", 404)
            try:
                coerced = _coerce_setting(key, value)
            except ValueError as exc:
                return _error(f"{key}: {exc}")
            if getattr(settings, key) != coerced:
                setattr(settings, key, coerced)
                changed.append(key)
        if changed:
            settings.save()
        if set(changed) & {"login_server_enabled", "login_server_host", "login_server_port"}:
            await self._twitch.apply_login_settings()
        if set(changed) & {"priority", "exclude", "priority_mode"}:
            # Rebuild wanted games and re-pick a channel without waiting for the
            # next scheduled inventory reload.
            self._twitch.change_state(State.GAMES_UPDATE)
        return web.json_response(
            {
                "ok": True,
                "changed": changed,
                "settings": _settings_data(settings),
            }
        )

    async def _select_channel(self, request: web.Request) -> web.Response:
        data, error = await self._json_object(request)
        if error is not None:
            return error
        twitch = self._twitch
        channel = None
        if "id" in data:
            try:
                channel = twitch.channels.get(int(data["id"]))
            except (TypeError, ValueError):
                return _error("id must be an integer")
        elif "login" in data:
            wanted = str(data["login"]).lower().lstrip("@")
            channel = next(
                (
                    candidate
                    for candidate in twitch.channels.values()
                    if candidate._login.lower() == wanted or candidate.name.lower() == wanted
                ),
                None,
            )
        else:
            return _error("pass the channel id or login")
        if channel is None:
            return _error("channel not found", 404)
        if not twitch.can_watch(channel):
            return _error(f"{channel.name} cannot earn any wanted drop right now", 409)
        twitch.gui.channels.request(channel)
        twitch.change_state(State.CHANNEL_SWITCH)
        return web.json_response({"ok": True, "channel": _channel_brief(channel)})

    async def _action(self, request: web.Request) -> web.Response:
        action = request.match_info["action"]
        twitch = self._twitch
        if action == "pause":
            twitch.stop_watching()
            twitch.change_state(State.IDLE)
            return web.json_response({"ok": True, "state": "IDLE"})
        if action == "resume":
            twitch.change_state(State.INVENTORY_FETCH)
            return web.json_response({"ok": True})
        if action in ("refresh", "reload"):
            twitch.change_state(State.INVENTORY_FETCH)
            return web.json_response({"ok": True})
        if action == "unwatch":
            twitch.stop_watching()
            return web.json_response({"ok": True})
        if action == "watch-campaign":
            # Quick-add from the campaign list: put the campaign's game on the
            # priority list (the panel's "mining list") and take it off the
            # exclude list, then let the engine rebuild wanted games now rather
            # than at the next scheduled reload.
            data, error = await self._json_object(request)
            if error is not None:
                return error
            campaign_id = data.get("campaign_id")
            campaign = (
                twitch._campaigns.get(str(campaign_id))
                if campaign_id is not None
                else None
            )
            if campaign is None:
                return _error("campaign not found", 404)
            game = campaign.game
            if game is None:
                return _error("this campaign has no game", 409)
            settings = twitch.settings
            priority = list(settings.priority)
            added = game.name not in priority
            if added:
                priority.append(game.name)
            exclude = set(settings.exclude)
            unexcluded = game.name in exclude
            exclude.discard(game.name)
            if added or unexcluded:
                settings.priority = priority
                settings.exclude = exclude
                settings.save()
                twitch.change_state(State.GAMES_UPDATE)
            return web.json_response(
                {
                    "ok": True,
                    "game": game.name,
                    "added": added,
                    "unexcluded": unexcluded,
                }
            )
        if action == "exit":
            # API clients only: stopping the miner also stops this dashboard,
            # so the web UI deliberately has no button for it.
            twitch.close()
            return web.json_response({"ok": True, "exiting": True})
        if action == "login-browser":
            reason = await twitch.start_browser_login()
            if reason is not None:
                return web.json_response(
                    {
                        "ok": False,
                        "reason": reason,
                        "message": start_reason(reason),
                    },
                    status=409,
                )
            return web.json_response({"ok": True})
        if action == "login-renew":
            reason = twitch.request_renewal()
            if reason is not None:
                return web.json_response(
                    {
                        "ok": False,
                        "reason": reason,
                        "message": start_reason(reason),
                    },
                    status=409,
                )
            return web.json_response({"ok": True})
        if action == "login-cancel":
            return web.json_response(
                {"ok": True, "cancelled": twitch.cancel_browser_login()}
            )
        if action == "claim":
            data, error = await self._json_object(request)
            if error is not None:
                return error
            drop_id = data.get("drop_id")
            drops = list(twitch.inventory)
            targets: list[TimedDrop] = []
            for campaign in drops:
                for drop in campaign.drops:
                    if not drop.can_claim:
                        continue
                    if drop_id is not None and drop.id != drop_id:
                        continue
                    targets.append(drop)
            if drop_id is not None and not targets:
                return _error("drop is not claimable", 409)
            claimed = 0
            failed = 0
            for drop in targets:
                if await drop.claim():
                    claimed += 1
                else:
                    failed += 1
            return web.json_response(
                {"ok": True, "claimed": claimed, "failed": failed, "targets": len(targets)}
            )
        return _error(f"unknown action: {action}", 404)

    # -- SSE ---------------------------------------------------------------

    async def _events(self, request: web.Request) -> web.StreamResponse:
        response = web.StreamResponse(
            headers={
                "Content-Type": "text/event-stream",
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            }
        )
        await response.prepare(request)
        self._streams.add(response)
        previous_logs: list[str] | None = None
        try:
            while not self._stop_event.is_set():
                status = json.dumps(_status_data(self._twitch), ensure_ascii=False)
                await response.write(f"event: status\ndata: {status}\n\n".encode("utf8"))
                logs = self._twitch.gui.output_buffer
                if logs != previous_logs:
                    payload = json.dumps({"lines": logs[-200:]}, ensure_ascii=False)
                    await response.write(f"event: logs\ndata: {payload}\n\n".encode("utf8"))
                    previous_logs = logs
                await response.write(b": keepalive\n\n")
                with suppress(asyncio.TimeoutError):
                    await asyncio.wait_for(
                        self._stop_event.wait(), timeout=EVENT_INTERVAL
                    )
        except (asyncio.CancelledError, ConnectionResetError, RuntimeError):
            # The browser closed the tab, or the server is shutting down.
            pass
        finally:
            self._streams.discard(response)
        return response

    # -- helpers -----------------------------------------------------------

    async def _json_object(
        self, request: web.Request
    ) -> tuple[dict[str, Any], web.Response | None]:
        try:
            data = await request.json()
        except Exception:
            return {}, _error("invalid JSON body")
        if not isinstance(data, dict):
            return {}, _error("expected a JSON object")
        return data, None
