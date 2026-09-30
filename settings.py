from __future__ import annotations

import json
from typing import Any, TypedDict, TYPE_CHECKING

from yarl import URL

from utils import json_load, json_save
from constants import SETTINGS_PATH, DEFAULT_LANG, PriorityMode

if TYPE_CHECKING:
    from main import ParsedArgs


class SettingsFile(TypedDict):
    proxy: URL
    language: str
    dark_mode: bool
    exclude: set[str]
    priority: list[str]
    autostart_tray: bool
    connection_quality: int
    tray_notifications: bool
    enable_badges_emotes: bool
    available_drops_check: bool
    priority_mode: PriorityMode
    reload_interval: int
    login_server_enabled: bool
    login_server_host: str
    login_server_port: int
    renewal_browser_path: str
    welcome_shown: bool


default_settings: SettingsFile = {
    "proxy": URL(),
    "priority": [],
    "exclude": set(),
    "dark_mode": False,
    "autostart_tray": False,
    "connection_quality": 1,
    "language": DEFAULT_LANG,
    "tray_notifications": True,
    "enable_badges_emotes": False,
    "available_drops_check": False,
    "priority_mode": PriorityMode.PRIORITY_ONLY,
    "reload_interval": 60,
    # The endpoint drives a browser that holds Twitch credentials, so it stays
    # off until a sign-in is actually asked for.
    "login_server_enabled": False,
    "login_server_host": "0.0.0.0",
    "login_server_port": 8090,
    # Empty means "find one": Chromium or Chrome on PATH, then the usual install
    # locations. Set it when renewal picks the wrong browser.
    "renewal_browser_path": "",
    # The first-run guide is shown once. Reset with `set welcome_shown false`.
    "welcome_shown": False,
}


class Settings:
    # from args
    log: bool
    tray: bool
    dump: bool
    # args properties
    debug_ws: int
    debug_gql: int
    logging_level: int
    # from settings file
    proxy: URL
    language: str
    dark_mode: bool
    exclude: set[str]
    priority: list[str]
    autostart_tray: bool
    connection_quality: int
    tray_notifications: bool
    enable_badges_emotes: bool
    available_drops_check: bool
    priority_mode: PriorityMode
    reload_interval: int
    login_server_enabled: bool
    login_server_host: str
    login_server_port: int
    renewal_browser_path: str
    welcome_shown: bool

    PASSTHROUGH = ("_settings", "_args", "_altered")

    # Settings that used to have another name. The endpoint was the login
    # helper's before it served the sign-in page.
    RENAMED = {
        "helper_server_enabled": "login_server_enabled",
        "helper_server_host": "login_server_host",
        "helper_server_port": "login_server_port",
    }

    def __init__(self, args: ParsedArgs):
        self._settings: SettingsFile = json_load(SETTINGS_PATH, default_settings)
        self._args: ParsedArgs = args
        self._altered: bool = False
        self._carry_over_renamed()

    def _carry_over_renamed(self) -> None:
        """
        Move any values the file still holds under an old name to the new one.

        The merge that loads the file drops keys it does not recognise, so this
        reads it separately - a port someone chose by hand should not quietly
        go back to the default because the setting was renamed.
        """
        try:
            raw = json.loads(SETTINGS_PATH.read_text("utf8"))
        except (OSError, ValueError):
            return
        if not isinstance(raw, dict):
            return
        for old, new in self.RENAMED.items():
            if old not in raw or raw[old] == default_settings[new]:
                continue
            # A value already set under the new name is the newer of the two,
            # and wins: only a setting still sitting at its default is one that
            # was never touched and so is safe to fill in.
            if self._settings[new] != default_settings[new]:
                continue
            self._settings[new] = raw[old]  # type: ignore[literal-required]
            self._altered = True

    # default logic of reading settings is to check args first, then the settings file
    def __getattr__(self, name: str, /) -> Any:
        if name in self.PASSTHROUGH:
            # passthrough
            return getattr(super(), name)
        elif hasattr(self._args, name):
            return getattr(self._args, name)
        elif name in self._settings:
            return self._settings[name]  # type: ignore[literal-required]
        return getattr(super(), name)

    def __setattr__(self, name: str, value: Any, /) -> None:
        if name in self.PASSTHROUGH:
            # passthrough
            return super().__setattr__(name, value)
        elif name in self._settings:
            self._settings[name] = value  # type: ignore[literal-required]
            self._altered = True
            return
        raise TypeError(f"{name} is missing a custom setter")

    def __delattr__(self, name: str, /) -> None:
        raise RuntimeError("settings can't be deleted")

    def alter(self) -> None:
        self._altered = True

    def save(self, *, force: bool = False) -> None:
        if self._altered or force:
            json_save(SETTINGS_PATH, self._settings, sort=True)
