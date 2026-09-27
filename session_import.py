"""
Imported browser session - the desktop login helper's captured request context.

Twitch gates the campaign catalog on the client an auth token was issued to, and
no client this app can log into by itself receives it any more. A separate
helper, run on a machine with a real browser, performs a genuine sign-in and
captures the complete request context Twitch's own web client used: a WEB client
OAuth token together with a fresh ``Client-Integrity`` proof, the device id, the
client session id and the exact user agent.

That context arrives over the network, so every field is treated as untrusted:
it is validated before it is stored, and again before it is used.
"""

from __future__ import annotations

import json
import math
import os
import re
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from types import MappingProxyType
from typing import Any, ClassVar, Mapping

import aiohttp

from constants import IMPORTED_SESSION_PATH, GQL_QUERIES, ClientType
from exceptions import MinerException


class SessionImportError(MinerException):
    """
    Raised when an imported session is missing, unreadable or not trustworthy.

    Only a fixed short code is ever surfaced - never the payload, which carries
    credentials.
    """

    def __init__(self, code: str):
        self.code: str = code
        super().__init__(f"Imported session rejected ({code})")


@dataclass(frozen=True)
class SessionBundle:
    """
    A captured browser request context, valid until ``expires_at``.

    ``headers`` is used verbatim: the whole point of the capture is that these
    values were produced together by one browser session. Combining them with
    anything else - another token, another device id, a token minted over plain
    HTTP - is what makes Twitch reject the request, so they are never merged.
    """

    captured_at: float
    expires_at: float
    user_agent: str
    headers: Mapping[str, str] = field(repr=False)

    # The integrity proof is bound to everything else in the set, and the whole
    # context stops working at once when it expires.
    MAX_BYTES: ClassVar[int] = 65536
    HEADER_NAMES: ClassVar[frozenset[str]] = frozenset({
        "authorization", "client-id", "client-integrity", "client-version",
        "client-session-id", "x-device-id", "device-id", "accept-language",
    })
    # What the capture is expected to look like; anything else is dropped rather
    # than forwarded to Twitch.
    AUTHORIZATION_RE: ClassVar[str] = r"OAuth [A-Za-z0-9_-]{1,512}"

    @classmethod
    def from_dict(cls, data: Any, *, now: float | None = None) -> SessionBundle:
        now = time() if now is None else now
        try:
            if not isinstance(data, dict) or set(data) != {
                "version", "captured_at", "expires_at", "user_agent", "headers",
            }:
                raise ValueError
            if type(data["version"]) is not int or data["version"] != 1:
                raise ValueError
            captured, expiry = data["captured_at"], data["expires_at"]
            if any(
                type(value) not in (int, float) or not math.isfinite(value)
                for value in (captured, expiry)
            ):
                raise ValueError
            # A capture is short-lived by nature; anything else is malformed.
            if not 0 < captured <= now + 60 or not 0 < expiry - captured <= 86400:
                raise ValueError
            user_agent, raw_headers = data["user_agent"], data["headers"]
            if not isinstance(raw_headers, dict):
                raise ValueError
            # Header names are case-insensitive on the wire.
            headers = {str(key).lower(): value for key, value in raw_headers.items()}
            if not set(headers) <= cls.HEADER_NAMES:
                raise ValueError
            for value in (user_agent, *headers.values()):
                if not isinstance(value, str) or not re.fullmatch(r"[\x20-\x7e]{1,16384}", value):
                    raise ValueError
            if len(user_agent) > 1024:
                raise ValueError
            if (
                headers.get("client-id") != ClientType.WEB.CLIENT_ID
                or not re.fullmatch(cls.AUTHORIZATION_RE, headers.get("authorization", ""))
                or not headers.get("client-integrity", "").strip()
                or not (headers.get("x-device-id") or headers.get("device-id"))
            ):
                raise ValueError
            if len(json.dumps(data).encode()) > cls.MAX_BYTES:
                raise ValueError
            return cls(
                float(captured), float(expiry), user_agent, MappingProxyType(headers)
            )
        except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
            raise SessionImportError("FORMAT") from None

    @property
    def token(self) -> str:
        """The bare OAuth token, without the ``OAuth `` prefix the header carries."""
        return self.headers["authorization"][6:]

    @property
    def device_id(self) -> str:
        return self.headers.get("x-device-id") or self.headers["device-id"]

    def is_fresh(self, now: float | None = None) -> bool:
        now = time() if now is None else now
        return self.expires_at > now

    def require_fresh(self, now: float | None = None) -> None:
        if not self.is_fresh(now):
            raise SessionImportError("EXPIRED")

    def request_headers(self) -> dict[str, str]:
        """
        The captured context, ready to send to gql.twitch.tv.

        ``Origin``/``Referer`` are what a browser on the Twitch site sends; the
        trailing slash matches the real thing.
        """
        return {
            **self.headers,
            "user-agent": self.user_agent,
            "origin": "https://www.twitch.tv",
            "referer": "https://www.twitch.tv/",
            "content-type": "application/json",
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "captured_at": self.captured_at,
            "expires_at": self.expires_at,
            "user_agent": self.user_agent,
            "headers": dict(self.headers),
        }


@dataclass(frozen=True)
class SDKCookie:
    """
    Twitch's SDK cookie, on the CDN host that issues the integrity proof.

    Renewal replays this into a browser so the proof is issued under the same
    SDK identity the capture used; without it there is nothing to renew from.
    """

    value: str = field(repr=False)
    expires_at: float

    NAME: ClassVar[str] = "KP_UIDz-ssn"
    DOMAIN: ClassVar[str] = "k.twitchcdn.net"
    URL: ClassVar[str] = "https://k.twitchcdn.net/"
    # Cookie-value safe characters only.
    VALUE_RE: ClassVar[str] = r"[\x21\x23-\x2b\x2d-\x3a\x3c-\x5b\x5d-\x7e]{1,8192}"

    @classmethod
    def from_dict(cls, data: Any) -> SDKCookie:
        try:
            if not isinstance(data, dict) or set(data) != {"value", "expires_at"}:
                raise ValueError
            value, expiry = data["value"], data["expires_at"]
            if (
                not isinstance(value, str)
                or not re.fullmatch(cls.VALUE_RE, value)
                or type(expiry) not in (int, float)
                or not math.isfinite(expiry)
                or expiry <= 0
            ):
                raise ValueError
            return cls(value, float(expiry))
        except (KeyError, TypeError, ValueError, OverflowError):
            raise SessionImportError("SDK_COOKIE") from None

    @classmethod
    def from_browser(cls, cookies: Any, *, now: float) -> SDKCookie:
        """Pick the one SDK cookie out of a CDP ``Network.getCookies`` reply."""
        if not isinstance(cookies, list):
            raise SessionImportError("SDK_COOKIE")
        candidates = [
            cookie for cookie in cookies
            if isinstance(cookie, dict)
            and cookie.get("name") == cls.NAME
            and cookie.get("domain") == cls.DOMAIN
            and cookie.get("path") == "/"
            and cookie.get("secure") is True
            and cookie.get("httpOnly") is True
        ]
        if len(candidates) != 1:
            raise SessionImportError("SDK_COOKIE")
        cookie = candidates[0]
        result = cls.from_dict(
            {"value": cookie.get("value"), "expires_at": cookie.get("expires")}
        )
        result.require_fresh(now)
        return result

    def is_fresh(self, now: float) -> bool:
        return self.expires_at > now

    def require_fresh(self, now: float) -> None:
        if not self.is_fresh(now):
            raise SessionImportError("SDK_EXPIRED")

    def to_dict(self) -> dict[str, Any]:
        return {"value": self.value, "expires_at": self.expires_at}

    def to_browser_cookie(self) -> dict[str, Any]:
        return {
            "name": self.NAME, "value": self.value, "expires": self.expires_at,
            "domain": self.DOMAIN, "path": "/", "secure": True,
            "httpOnly": True, "sameSite": "None",
        }


@dataclass(frozen=True)
class ServerSeed:
    """
    Everything renewal needs: the context to refresh, and the SDK identity to
    present while doing it.
    """

    bundle: SessionBundle
    cookie: SDKCookie | None

    @classmethod
    def from_dict(cls, data: Any, *, now: float | None = None) -> ServerSeed:
        """Parse the shape the helper uploads, where the cookie is required."""
        seed = cls._parse(data, now=now)
        if seed.cookie is None:
            raise SessionImportError("SDK_SEED")
        return seed

    @classmethod
    def from_stored(cls, data: Any, *, now: float | None = None) -> ServerSeed:
        """
        Parse our own storage, which may hold a session with no SDK identity.

        Such a session still works - it just cannot be renewed, so it expires and
        the saved login takes over.
        """
        return cls._parse(data, now=now)

    @classmethod
    def _parse(cls, data: Any, *, now: float | None = None) -> ServerSeed:
        now = time() if now is None else now
        try:
            if not isinstance(data, dict) or set(data) != {"version", "bundle", "sdk_cookie"}:
                raise ValueError
            if type(data["version"]) is not int or data["version"] != 1:
                raise ValueError
            if len(json.dumps(data).encode()) > SessionBundle.MAX_BYTES:
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError, RecursionError):
            raise SessionImportError("SDK_SEED") from None
        bundle = SessionBundle.from_dict(data["bundle"], now=now)
        raw_cookie = data["sdk_cookie"]
        cookie = None if raw_cookie is None else SDKCookie.from_dict(raw_cookie)
        return cls(bundle, cookie)

    def to_dict(self) -> dict[str, Any]:
        return {
            "version": 1,
            "bundle": self.bundle.to_dict(),
            "sdk_cookie": self.cookie.to_dict() if self.cookie is not None else None,
        }


async def probe_bundle(bundle: SessionBundle, session: aiohttp.ClientSession) -> int:
    """
    Prove that a captured context still works, and return its user ID.

    Both checks run against the originating Twitch endpoints with exactly the
    captured headers: an integrity proof only holds for the context it was
    issued in, so nothing here may substitute its own values.
    """
    try:
        async with session.get(
            "https://id.twitch.tv/oauth2/validate",
            headers={
                "Authorization": bundle.headers["authorization"],
                "User-Agent": bundle.user_agent,
            },
        ) as response:
            if response.status != 200:
                raise SessionImportError("AUTH")
            identity = await response.json()
        if (
            not isinstance(identity, dict)
            or identity.get("client_id") != ClientType.WEB.CLIENT_ID
        ):
            raise SessionImportError("IDENTITY")
        raw_user_id = identity.get("user_id")
        if not isinstance(raw_user_id, str) or not raw_user_id.isdecimal():
            raise SessionImportError("IDENTITY")
        user_id = int(raw_user_id)
        if user_id <= 0:
            raise SessionImportError("IDENTITY")
        async with session.post(
            "https://gql.twitch.tv/gql",
            headers=bundle.request_headers(),
            json=[GQL_QUERIES["Inventory"], GQL_QUERIES["Campaigns"]],
        ) as response:
            if response.status != 200:
                raise SessionImportError("REQUEST")
            results = await response.json()
        # The whole point of the import is the campaign catalog, so refuse a
        # context that cannot read it. An empty list is a valid answer.
        if not isinstance(results, list) or len(results) != 2:
            raise SessionImportError("CATALOG")
        for row in results:
            if not isinstance(row, dict) or row.get("errors"):
                raise SessionImportError("CATALOG")
        catalog = ((results[1].get("data") or {}).get("currentUser") or {}).get("dropCampaigns")
        if not isinstance(catalog, list):
            raise SessionImportError("CATALOG")
    except aiohttp.ClientError:
        raise SessionImportError("REQUEST") from None
    except (ValueError, TypeError, KeyError, AttributeError):
        raise SessionImportError("RESPONSE") from None
    return user_id


class PrivateSessionFile:
    """
    Owner-only JSON storage for the imported session and its renewal state.

    The stored object holds credentials, so the file is created 0600 by
    ``mkstemp`` and only then written - chmod after writing would leave a window
    where it is world-readable.
    """

    def __init__(self, path: Path = IMPORTED_SESSION_PATH):
        self.path: Path = path

    def stat_key(self) -> tuple[int, int] | None:
        """Identity of the stored file, for cheap change detection."""
        try:
            stat = self.path.stat()
        except OSError:
            return None
        return stat.st_mtime_ns, stat.st_size

    def read(self) -> ServerSeed:
        try:
            with self.path.open("rb") as stream:
                raw = stream.read(SessionBundle.MAX_BYTES + 1)
            if len(raw) > SessionBundle.MAX_BYTES:
                raise ValueError
            data = json.loads(raw)
        except FileNotFoundError:
            raise SessionImportError("MISSING") from None
        except (OSError, ValueError, UnicodeError, RecursionError):
            raise SessionImportError("FILE") from None
        # Files written before renewal existed hold a bare bundle; they still
        # describe a usable session, just one that cannot be renewed.
        if isinstance(data, dict) and "headers" in data:
            return ServerSeed(SessionBundle.from_dict(data), None)
        return ServerSeed.from_stored(data)

    def write(self, seed: ServerSeed) -> None:
        name = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(prefix=".tdm-session-", dir=self.path.parent)
            with os.fdopen(fd, "w", encoding="utf8") as stream:
                json.dump(seed.to_dict(), stream, allow_nan=False)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        except (OSError, ValueError, TypeError):
            raise SessionImportError("SAVE") from None
        finally:
            if name is not None:
                Path(name).unlink(missing_ok=True)

    def remove(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError:
            raise SessionImportError("SAVE") from None
