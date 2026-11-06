"""
Local cache for the dashboard's reward and campaign artwork.

The dashboard is usually opened from the same network as the miner, while the
images live on Twitch's CDN. Fetching them through the miner keeps the page
usable when the CDN is slow or blocked, and makes a second visit free.

The cache is never a substitute for the inventory: a file is only served while
its URL is part of a campaign currently known to the miner. ``sync`` is called
when the campaign list is fetched and by a periodic task, so images belonging to
campaigns that ended are removed automatically.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
from contextlib import suppress
from pathlib import Path
from typing import TYPE_CHECKING, Any

from yarl import URL

from twitchdropsminer.common.constants import CACHE_PATH

if TYPE_CHECKING:
    from collections import abc

    from twitchdropsminer.core.twitch import Twitch


logger = logging.getLogger("TwitchDrops")

IMAGE_NAME = re.compile(r"[0-9a-f]{64}\.(?:jpg|jpeg|png|gif|webp)")
IMAGE_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif", ".webp")
MAX_IMAGE_BYTES = 8 * 1024 * 1024
# At most this many images are downloaded at the same time.
MAX_DOWNLOADS = 4
# How often unreferenced files are swept even if no dashboard is open.
SWEEP_INTERVAL = 30 * 60


class ImageCache:
    def __init__(
        self,
        twitch: Twitch,
        *,
        directory: Path | None = None,
        manifest: Path | None = None,
    ) -> None:
        self._twitch = twitch
        self.directory: Path = Path(directory or CACHE_PATH / "images")
        self.manifest_path: Path = Path(manifest or CACHE_PATH / "images.json")
        self.directory.mkdir(parents=True, exist_ok=True)
        self._urls: dict[str, str] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._semaphore = asyncio.Semaphore(MAX_DOWNLOADS)
        self._dirty = False
        self._load()

    # -- manifest ----------------------------------------------------------

    def _load(self) -> None:
        try:
            data = json.loads(self.manifest_path.read_text("utf8"))
        except (OSError, ValueError):
            return
        if not isinstance(data, dict):
            return
        for key, value in data.items():
            if (
                isinstance(key, str)
                and re.fullmatch(r"[0-9a-f]{64}", key)
                and isinstance(value, str)
            ):
                self._urls[key] = value

    def _save(self) -> None:
        if not self._dirty:
            return
        try:
            self.manifest_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.manifest_path.with_name(self.manifest_path.name + ".new")
            temporary.write_text(
                json.dumps(self._urls, indent=2, sort_keys=True), "utf8"
            )
            os.replace(temporary, self.manifest_path)
            self._dirty = False
        except OSError:
            logger.warning("Could not write the image cache manifest")

    def save(self) -> None:
        """Persist registrations made by ``url_for`` since the last write."""
        self._save()

    # -- URLs --------------------------------------------------------------

    @staticmethod
    def _name(url: str) -> str | None:
        try:
            parsed = URL(url)
        except ValueError:
            return None
        if parsed.scheme not in ("http", "https") or not parsed.host:
            return None
        suffix = parsed.suffix.lower()
        if suffix not in IMAGE_SUFFIXES:
            suffix = ".jpg"
        digest = hashlib.sha256(url.encode("utf8")).hexdigest()
        return f"{digest}{suffix}"

    def url_for(self, url: str) -> str:
        """Register an image and return the dashboard-relative path for it."""
        if not url:
            return ""
        name = self._name(url)
        if name is None:
            return url
        digest = name.split(".", 1)[0]
        if self._urls.get(digest) != url:
            self._urls[digest] = url
            self._dirty = True
        return f"/images/{name}"

    # -- cleanup -----------------------------------------------------------

    def _collect(self, current: dict[str, str], url: str) -> None:
        if not url:
            return
        name = self._name(url)
        if name is not None:
            current[name.split(".", 1)[0]] = url

    def sync(self, inventory: abc.Iterable[Any]) -> None:
        """
        Keep only images belonging to the campaigns currently known.

        An empty inventory is not treated as "everything ended": a failed
        catalogue fetch must not wipe the cache.
        """
        current: dict[str, str] = {}
        for campaign in inventory:
            self._collect(current, str(campaign.image_url))
            for drop in campaign.drops:
                for benefit in drop.benefits:
                    self._collect(current, str(benefit.image_url))
        if not current:
            return

        changed = False
        for digest, url in current.items():
            if self._urls.get(digest) != url:
                self._urls[digest] = url
                changed = True
        for path in self.directory.iterdir():
            if not path.is_file() or path.suffix == ".tmp":
                continue
            if path.stem not in current:
                with suppress(OSError):
                    path.unlink()
                    changed = True
        for digest in list(self._urls):
            if digest not in current:
                del self._urls[digest]
                changed = True
        if changed:
            self._dirty = True
        self._save()

    # -- serving -----------------------------------------------------------

    def path_for(self, name: str) -> Path | None:
        """An already cached file, without touching the network."""
        path = self.directory / name
        return path if path.is_file() else None

    async def fetch(self, name: str) -> Path | None:
        """Return a cached file, downloading it once if necessary."""
        path = self.path_for(name)
        if path is not None:
            return path
        digest = name.split(".", 1)[0]
        url = self._urls.get(digest)
        if url is None:
            return None

        lock = self._locks.setdefault(digest, asyncio.Lock())
        async with lock:
            path = self.path_for(name)
            if path is not None:
                return path
            async with self._semaphore:
                data = await self._download(url)
            if data is None:
                return None
            target = self.directory / name
            try:
                temporary = target.with_name(target.name + ".tmp")
                temporary.write_bytes(data)
                os.replace(temporary, target)
            except OSError:
                logger.warning(f"Could not cache an image at {target}")
                return None
            return target

    async def _download(self, url: str) -> bytes | None:
        try:
            async with self._twitch.request("GET", url) as response:
                if response.status != 200:
                    return None
                data = await response.read()
        except Exception as error:
            logger.debug(f"Image download failed ({type(error).__name__}): {url}")
            return None
        if not data or len(data) > MAX_IMAGE_BYTES:
            return None
        return data

    async def run(self, interval: float = SWEEP_INTERVAL) -> None:
        while True:
            await asyncio.sleep(interval)
            try:
                self.sync(self._twitch.inventory)
            except Exception:
                logger.exception("Image cache cleanup failed")
