"""
Keep an imported session alive by re-issuing its integrity proof.

The proof is short-lived and Twitch only accepts one that a real browser issued
while running Kasada's script, so renewal starts a throwaway headless Chromium,
replays the captured context into it, and lets the page mint a replacement. The
result is checked against the response the network layer saw - the two have to
agree, which is what makes a replayed or cached answer useless to an attacker.

Nothing here talks to Twitch over plain HTTP on the miner's behalf: the browser
is the only thing that ever presents the credentials.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from time import time
from typing import Any

import aiohttp

from browser_cdp import (
    INTEGRITY_URL,
    OwnedChromium,
    browser_target,
    find_browser,
)
from session_import import (
    SDKCookie,
    ServerSeed,
    SessionBundle,
    PrivateSessionFile,
    probe_bundle,
    SessionImportError,
)
from constants import IMPORTED_SESSION_PATH


logger = logging.getLogger("TwitchDrops")

# The page whose origin the issuance has to run on. Its contents are never
# fetched - the request is fulfilled locally with a blank document.
PAGE = "https://www.twitch.tv/drops/campaigns"

# Kasada's loader, as served to the Twitch web client.
SDK_SCRIPT = (
    "https://k.twitchcdn.net/149e9513-01fa-4fb0-aad4-566afd725d1b/"
    "2d206a39-8ed7-437e-a3be-862e0f06eea3/p.js"
)

STUB_PAGE = b"<!doctype html><html><body></body></html>"

# Renewal reports a short code so the UI can translate it; the log gets the full
# sentence from here, because a log line is read by a person debugging and can
# afford to be explicit.
UNAVAILABLE_LOGS = {
    "no-session": "no session has been imported yet",
    "no-sdk-cookie": (
        "the imported session has no SDK cookie, so it cannot be renewed -"
        " sign in again"
    ),
    "no-browser": "no Chromium-based browser was found on this machine",
    "sdk-expired": (
        "the stored SDK cookie has expired, so it cannot be renewed -"
        " sign in again"
    ),
    "not-running": "the renewal task is not running",
}


class SDKExchange:
    """Correlate a POST issuance with its uncached network response."""

    def __init__(self):
        self.posts: set[str] = set()
        self.responses: dict[str, dict[str, Any]] = {}
        self.cached: set[str] = set()
        self.loaded = asyncio.Event()
        self.proof: asyncio.Future[Any] = asyncio.get_running_loop().create_future()

    async def run(self, protocol: Any) -> None:
        while True:
            event = await protocol.events.get()
            if event is None:
                raise SessionImportError("BROWSER_PROTOCOL")
            method, params = event["method"], event["params"]
            request_id = params.get("requestId")
            if len(self.posts) + len(self.responses) + len(self.cached) > 256:
                raise SessionImportError("CAPTURE_LIMIT")
            if method == "Fetch.requestPaused":
                request = params["request"]
                if (
                    request.get("url") != PAGE
                    or request.get("method") != "GET"
                    or params.get("resourceType") != "Document"
                ):
                    raise SessionImportError("SDK_PAGE")
                await protocol.command("Fetch.fulfillRequest", {
                    "requestId": request_id, "responseCode": 200,
                    "responseHeaders": [
                        {"name": "Content-Type", "value": "text/html; charset=utf-8"}
                    ],
                    "body": base64.b64encode(STUB_PAGE).decode(),
                })
            elif method == "Page.loadEventFired":
                self.loaded.set()
            elif method == "Network.requestWillBeSent":
                request = params["request"]
                if request.get("url") == INTEGRITY_URL and request.get("method") == "POST":
                    self.posts.add(request_id)
            elif method == "Network.requestServedFromCache":
                self.cached.add(request_id)
            elif method == "Network.responseReceived" and request_id in self.posts:
                self.responses[request_id] = params["response"]
            elif method == "Network.loadingFailed" and request_id in self.posts:
                raise SessionImportError("SDK_ISSUANCE")
            elif method == "Network.loadingFinished" and request_id in self.posts:
                response = self.responses.get(request_id, {})
                if (
                    response.get("url") != INTEGRITY_URL
                    or response.get("status") != 200
                    or response.get("fromDiskCache")
                    or response.get("fromServiceWorker")
                    or request_id in self.cached
                ):
                    raise SessionImportError("SDK_ISSUANCE")
                data = await protocol.body(request_id)
                if not self.proof.done():
                    self.proof.set_result(data)


class SDKAcquisition:
    """Ask a page in the owned browser to mint a fresh integrity proof."""

    EVENTS = frozenset({
        "Fetch.requestPaused", "Page.loadEventFired",
        "Network.requestServedFromCache", "Network.loadingFailed",
    })
    SCRIPT = """async function(headers, sdk) {
      return await new Promise(resolve => {
        const deadline = setTimeout(() => resolve({failure: 'sdk_timeout'}), 90000);
        const finish = value => { clearTimeout(deadline); resolve(value); };
        document.addEventListener('kpsdk-load', () => window.KPSDK.configure([
          {protocol: 'https:', method: 'POST', domain: 'gql.twitch.tv', path: '/integrity'}
        ]), {once: true});
        document.addEventListener('kpsdk-ready', async () => {
          try {
            const r = await window.fetch('https://gql.twitch.tv/integrity', {
              method: 'POST', headers, body: null, credentials: 'omit', mode: 'cors',
              signal: AbortSignal.timeout(30000)
            });
            finish({status: r.status, data: await r.json()});
          } catch (_) { finish({failure: 'issuance_fetch'}); }
        }, {once: true});
        const script = document.createElement('script');
        script.onerror = () => finish({failure: 'sdk_script'});
        script.src = sdk;
        document.body.appendChild(script);
      });
    }"""

    def __init__(self, *, clock: Callable[[], float] = time, timeout: float = 120):
        self.clock: Callable[[], float] = clock
        self.timeout: float = timeout

    async def run(
        self, protocol: Any, original: SessionBundle,
        cookie: SDKCookie | None = None, *, initial: bool = False,
    ) -> ServerSeed:
        try:
            return await asyncio.wait_for(
                self._run(protocol, original, cookie, initial=initial), self.timeout
            )
        except (TimeoutError, asyncio.TimeoutError):
            raise SessionImportError("SDK_TIMEOUT") from None
        except (KeyError, TypeError, ValueError, AttributeError):
            raise SessionImportError("BROWSER_PROTOCOL") from None

    async def _run(
        self, protocol: Any, original: SessionBundle,
        previous_cookie: SDKCookie | None, *, initial: bool,
    ) -> ServerSeed:
        exchange = SDKExchange()
        events = asyncio.create_task(exchange.run(protocol))
        acquire = asyncio.create_task(
            self._acquire(protocol, exchange, original, previous_cookie, initial=initial)
        )
        try:
            done, _ = await asyncio.wait({events, acquire}, return_when=asyncio.FIRST_COMPLETED)
            if events in done:
                await events
                raise SessionImportError("BROWSER_PROTOCOL")
            return await acquire
        finally:
            for task in (events, acquire):
                task.cancel()
            await asyncio.gather(events, acquire, return_exceptions=True)
            exchange.proof.cancel()

    async def _acquire(
        self, protocol: Any, exchange: SDKExchange, original: SessionBundle,
        previous_cookie: SDKCookie | None, *, initial: bool,
    ) -> ServerSeed:
        await protocol.command("Network.enable")
        await protocol.command("Network.setCacheDisabled", {"cacheDisabled": True})
        await protocol.command("Network.setBypassServiceWorker", {"bypass": True})
        if previous_cookie is not None:
            previous_cookie.require_fresh(self.clock())
            await protocol.command(
                "Network.setCookies", {"cookies": [previous_cookie.to_browser_cookie()]}
            )
        await protocol.command("Page.enable")
        await protocol.command("Fetch.enable", {"patterns": [{
            "urlPattern": PAGE, "resourceType": "Document", "requestStage": "Request",
        }]})
        await protocol.command("Page.navigate", {"url": PAGE})
        await exchange.loaded.wait()
        result = await protocol.command(
            "Runtime.evaluate", {"expression": "navigator.userAgent", "returnByValue": True}
        )
        user_agent = result["result"]["value"]
        result = await protocol.command("Runtime.evaluate", {"expression": "globalThis"})
        # The proof is issued for the exact headers the capture used, minus the
        # proof itself - sending the old one would make the SDK replay it.
        headers = {key: value for key, value in original.headers.items() if key != "client-integrity"}
        result = await protocol.command("Runtime.callFunctionOn", {
            "objectId": result["result"]["objectId"], "functionDeclaration": self.SCRIPT,
            "arguments": [{"value": headers}, {"value": SDK_SCRIPT}],
            "awaitPromise": True, "returnByValue": True,
        }, timeout=self.timeout)
        acquired = result.get("result", {}).get("value")
        if (
            result.get("exceptionDetails")
            or not isinstance(acquired, dict)
            or acquired.get("failure")
            or acquired.get("status") != 200
        ):
            raise SessionImportError("SDK_ISSUANCE")
        data = acquired.get("data")
        observed = await exchange.proof
        # The page's own report and the network layer's copy must agree; a
        # mismatch means one of them is not a genuine issuance.
        if (
            not isinstance(data, dict) or not isinstance(observed, dict)
            or data.get("token") != observed.get("token")
            or data.get("expiration") != observed.get("expiration")
            or type(data.get("expiration")) not in (int, float)
        ):
            raise SessionImportError("SDK_ISSUANCE")
        bundle = SessionBundle.from_dict({
            "version": 1, "captured_at": self.clock(), "expires_at": data["expiration"] / 1000,
            "user_agent": user_agent,
            "headers": {**headers, "client-integrity": data.get("token")},
        }, now=self.clock())
        minimum_expiry = self.clock() + 30
        if previous_cookie is not None and not initial:
            minimum_expiry = max(minimum_expiry, original.expires_at)
        if (
            bundle.headers["client-integrity"] == original.headers["client-integrity"]
            or bundle.expires_at <= minimum_expiry
        ):
            raise SessionImportError("REPLAY")
        result = await protocol.command("Network.getCookies", {"urls": [SDKCookie.URL]})
        cookie = SDKCookie.from_browser(result.get("cookies"), now=self.clock())
        if cookie.expires_at <= max(
            previous_cookie.expires_at if previous_cookie and not initial else 0,
            bundle.expires_at,
        ):
            raise SessionImportError("SDK_COOKIE")
        return ServerSeed(bundle, cookie)


class SDKIssuer:
    """Issue one proof in an owned temporary browser."""

    def __init__(self, browser: OwnedChromium, *, timeout: float = 120):
        self.browser: OwnedChromium = browser
        self.timeout: float = timeout

    async def issue(self, seed: ServerSeed, *, initial: bool = False) -> ServerSeed:
        if seed.cookie is None:
            raise SessionImportError("SDK_SEED")
        seed.cookie.require_fresh(time())
        async with self.browser.start() as address:
            async with browser_target(address, extra_events=SDKAcquisition.EVENTS) as protocol:
                return await SDKAcquisition(timeout=self.timeout).run(
                    protocol, seed.bundle, seed.cookie, initial=initial
                )


async def _probe(bundle: SessionBundle) -> int:
    async with aiohttp.ClientSession(
        timeout=aiohttp.ClientTimeout(total=30),
        cookie_jar=aiohttp.DummyCookieJar(),
        headers={"Accept": "*/*", "Accept-Encoding": "gzip"},
    ) as http:
        return await probe_bundle(bundle, http)


class SessionRenewal:
    """
    Renew the imported session shortly before it expires.

    Runs as one task for as long as the miner does. A renewal that cannot be
    performed is not fatal: it reports why, keeps retrying with a backoff, and
    the miner falls back to the saved login once the session runs out.
    """

    RENEW_BEFORE = 300.0
    # How long to wait before looking at the stored session again, when there is
    # nothing to renew (no sign-in yet, or no SDK cookie to renew with).
    IDLE_POLL = 60.0
    # A session is worth renewing for a long time; failures step back rather than
    # hammering Twitch.
    RETRY_MAX = 900.0

    def __init__(
        self,
        *,
        browser_path: str = "",
        session_file: Path = IMPORTED_SESSION_PATH,
        on_renewed: Callable[[int], None] = lambda user_id: None,
        probe: Callable[[SessionBundle], Any] = _probe,
        clock: Callable[[], float] = time,
    ):
        self.browser_path: str = browser_path
        self._file = PrivateSessionFile(session_file)
        self.on_renewed = on_renewed
        self.probe = probe
        self.clock = clock
        self._task: asyncio.Task | None = None
        self._stopping = False
        self._wake = asyncio.Event()
        self._force = False
        self.last_error: str | None = None
        self.last_renewed_at: float | None = None
        self._unavailable: str | None = None

    # -- status ------------------------------------------------------------

    @property
    def unavailable_reason(self) -> str | None:
        """Why renewal cannot run, as a short code, or None when it can."""
        return self._unavailable

    def _set_unavailable(self, code: str | None) -> None:
        if code != self._unavailable:
            if code is not None:
                logger.warning(
                    "Session renewal is unavailable:"
                    f" {UNAVAILABLE_LOGS.get(code, code)}"
                )
            else:
                logger.info("Session renewal is available")
            self._unavailable = code

    # -- lifecycle ---------------------------------------------------------

    def start(self) -> None:
        if self._task is None and not self._stopping:
            self._task = asyncio.create_task(self._run())

    async def stop(self) -> None:
        self._stopping = True
        self._wake.set()
        if self._task is not None:
            self._task.cancel()
            await asyncio.gather(self._task, return_exceptions=True)
            self._task = None

    def notify_changed(self) -> None:
        """A new session was stored; re-read it and reschedule."""
        self._wake.set()

    def request_renewal(self) -> None:
        """
        Renew now instead of waiting for the deadline.

        Renewal normally happens hours after a login, which makes it awkward to
        check that it works at all.
        """
        self._force = True
        self._wake.set()

    # -- loop --------------------------------------------------------------

    async def _wait(self, delay: float) -> bool:
        """Sleep, unless something changed. True when woken early."""
        try:
            await asyncio.wait_for(self._wake.wait(), timeout=delay)
        except (TimeoutError, asyncio.TimeoutError):
            return False
        finally:
            self._wake.clear()
        return True

    def _read_seed(self) -> ServerSeed | None:
        try:
            return self._file.read()
        except SessionImportError:
            return None

    def can_renew(self) -> str | None:
        """
        Why renewal cannot run right now, as a short code, or None when it can.

        A code rather than a sentence: the caller may be putting this in front of
        a user, and that text has to be translatable. The wording for the log -
        which is English by design and wants to be more explicit - lives in
        `UNAVAILABLE_LOGS`.

        Reads the stored session directly rather than reporting a cached verdict,
        so a request made before the loop has had its first look gets the truth.
        """
        seed = self._read_seed()
        if seed is None:
            return "no-session"
        if seed.cookie is None:
            return "no-sdk-cookie"
        if not find_browser(self.browser_path):
            return "no-browser"
        return None

    def can_revive(self) -> bool:
        """
        Whether an expired stored proof could be replaced by a renewal.

        What a short outage leaves behind: the proof itself lives an hour or so,
        while the SDK cookie it was minted with lives a day, so "expired but
        renewable" is an ordinary state rather than a dead end. Narrower than
        `can_renew`, which also says yes to a session that is perfectly fresh.
        """
        if self.can_renew() is not None:
            return False
        seed = self._read_seed()
        if seed is None or seed.cookie is None:
            return False
        # Both halves matter: a proof past its date is the thing being replaced,
        # and a cookie past its date is what there is nothing left to mint from.
        # `can_renew` only asks whether a cookie is there at all.
        return (
            not seed.bundle.is_fresh(self.clock())
            and seed.cookie.is_fresh(self.clock())
        )

    async def _run(self) -> None:
        retry = 5.0
        while not self._stopping:
            reason = self.can_renew()
            if reason is not None:
                self._set_unavailable(reason)
                await self._wait(self.IDLE_POLL)
                continue
            self._set_unavailable(None)
            seed = self._read_seed()
            assert seed is not None
            forced, self._force = self._force, False
            delay = max(0.0, seed.bundle.expires_at - self.clock() - self.RENEW_BEFORE)
            if not forced and delay > 0 and await self._wait(delay):
                continue
            try:
                await self._renew(seed)
                retry = 5.0
            except SessionImportError as error:
                self.last_error = error.code
                if error.code in ("SDK_EXPIRED", "SDK_SEED"):
                    # Nothing left to renew from; wait for a new sign-in.
                    self._set_unavailable("sdk-expired")
                    await self._wait(self.IDLE_POLL)
                    continue
                if error.code == "BROWSER_START":
                    # The usual causes are a browser that is not really there (a
                    # snap or flatpak wrapper), or missing shared libraries on a
                    # minimal server - neither of which the error code says.
                    logger.warning(
                        "The browser used for renewal would not start. Check that"
                        " Chromium or Chrome is installed with its runtime"
                        " dependencies, and point renewal_browser_path at a real"
                        " executable if it lives somewhere unusual."
                    )
                logger.warning(
                    f"Session renewal failed ({error.code}), retrying in {retry:.0f}s"
                )
                await self._wait(retry)
                retry = min(self.RETRY_MAX, retry * 2)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.last_error = "UNEXPECTED"
                logger.exception("Session renewal failed unexpectedly")
                await self._wait(retry)
                retry = min(self.RETRY_MAX, retry * 2)

    async def _renew(self, seed: ServerSeed) -> None:
        executable = find_browser(self.browser_path)
        if executable is None:
            raise SessionImportError("BROWSER_MISSING")
        issuer = SDKIssuer(
            # Chromium refuses its sandbox when running as root, which is the
            # normal case in a container.
            OwnedChromium(executable, no_sandbox=os.name == "posix" and os.geteuid() == 0),
        )
        renewed = await issuer.issue(seed)
        # Prove the replacement works before adopting it - a proof that Twitch
        # rejects would otherwise replace one that still had minutes left.
        user_id = await self.probe(renewed.bundle)
        renewed.bundle.require_fresh(self.clock())
        self._file.write(renewed)
        self.last_renewed_at = self.clock()
        self.last_error = None
        logger.info(
            f"Renewed the imported session, valid for another"
            f" {(renewed.bundle.expires_at - self.clock()) / 3600:.1f}h"
        )
        self.on_renewed(user_id)
