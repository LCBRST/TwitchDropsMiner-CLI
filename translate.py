from __future__ import annotations

from collections import abc
from typing import Any, TypedDict, TYPE_CHECKING

from exceptions import MinerException
from utils import json_load, json_save
from constants import IS_PACKAGED, LANG_PATH, DEFAULT_LANG

if TYPE_CHECKING:
    from typing_extensions import NotRequired

class StatusMessages(TypedDict):
    terminated: str
    watching: str
    goes_online: str
    goes_offline: str
    claimed_drop: str
    no_channel: str
    no_campaign: str

class ChromeMessages(TypedDict):
    startup: str
    login_to_complete: str
    no_token: str
    closed_window: str

class LoginMessages(TypedDict):
    chrome: ChromeMessages
    error_code: str
    unexpected_content: str
    email_code_required: str
    twofa_code_required: str
    incorrect_login_pass: str
    incorrect_email_code: str
    incorrect_twofa_code: str

class ErrorMessages(TypedDict):
    captcha: str
    no_connection: str
    site_down: str

class GUIStatus(TypedDict):
    name: str
    idle: str
    exiting: str
    terminated: str
    cleanup: str
    gathering: str
    switching: str
    fetching_inventory: str
    fetching_campaigns: str
    adding_campaigns: str

class GUITabs(TypedDict):
    main: str
    inventory: str
    settings: str
    help: str

class GUITray(TypedDict):
    notification_title: str
    minimize: str
    show: str
    quit: str

class GUILoginForm(TypedDict):
    name: str
    labels: str
    logging_in: str
    logged_in: str
    logged_out: str
    request: str
    required: str
    username: str
    password: str
    twofa_code: str
    button: str

class GUIWebsocket(TypedDict):
    name: str
    websocket: str
    initializing: str
    connected: str
    disconnected: str
    connecting: str
    disconnecting: str
    reconnecting: str

class GUIProgress(TypedDict):
    name: str
    drop: str
    game: str
    campaign: str
    remaining: str
    drop_progress: str
    campaign_progress: str

class GUIChannelHeadings(TypedDict):
    channel: str
    status: str
    game: str
    viewers: str

class GUIChannels(TypedDict):
    name: str
    switch: str
    online: str
    pending: str
    offline: str
    headings: GUIChannelHeadings

class GUIInvFilter(TypedDict):
    name: str
    show: str
    not_linked: str
    upcoming: str
    expired: str
    excluded: str
    finished: str
    refresh: str

class GUIInvStatus(TypedDict):
    linked: str
    not_linked: str
    active: str
    expired: str
    upcoming: str
    claimed: str
    ready_to_claim: str

class GUIInventory(TypedDict):
    filter: GUIInvFilter
    status: GUIInvStatus
    starts: str
    ends: str
    allowed_channels: str
    all_channels: str
    and_more: str
    percent_progress: str
    minutes_progress: str

class GUISettingsGeneral(TypedDict):
    name: str
    autostart: str
    tray: str
    tray_notifications: str
    dark_mode: str
    priority_mode: str
    proxy: str

class GUISettingsAdvanced(TypedDict):
    name: str
    warning: str
    warning_text: str
    enable_badges_emotes: str
    available_drops_check: str

class GUIPriorityModes(TypedDict):
    priority_only: str
    ending_soonest: str
    low_availability: str

class GUISettings(TypedDict):
    general: GUISettingsGeneral
    advanced: GUISettingsAdvanced
    priority_modes: GUIPriorityModes
    game_name: str
    priority: str
    exclude: str
    reload: str
    reload_text: str

class GUIHelpLinks(TypedDict):
    name: str
    inventory: str
    campaigns: str

class GUIHelp(TypedDict):
    links: GUIHelpLinks
    how_it_works: str
    how_it_works_text: str
    getting_started: str
    getting_started_text: str

class GUIMessages(TypedDict):
    output: str
    status: GUIStatus
    tabs: GUITabs
    tray: GUITray
    login: GUILoginForm
    websocket: GUIWebsocket
    progress: GUIProgress
    channels: GUIChannels
    inventory: GUIInventory
    settings: GUISettings
    help: GUIHelp

class CLILoginMessages(TypedDict):
    status: str
    status_id: str
    header: str
    step_open: str
    step_code: str
    step_approve: str

class CLIDropMessages(TypedDict):
    cleared: str
    active: str

class CLIWatchMessages(TypedDict):
    watching: str
    cleared: str

class CLIWSMessages(TypedDict):
    status: str
    removed: str

class CLIMessages(TypedDict):
    banner: str
    separator: str
    eof: str
    status: str
    notify: str
    drop: CLIDropMessages
    watch: CLIWatchMessages
    ws: CLIWSMessages
    login: CLILoginMessages
    commands: dict[str, str]

class Translation(TypedDict):
    language_name: NotRequired[str]
    english_name: str
    status: StatusMessages
    login: LoginMessages
    error: ErrorMessages
    gui: GUIMessages
    cli: NotRequired[CLIMessages]

default_cli_translation: CLIMessages = {
    "banner": "TwitchDropsMiner {version} (CLI)",
    "separator": "=" * 60,
    "eof": "Got EOF on stdin — closing.",
    "status": "[status] {text}",
    "status_progress": "[status] {text} {bar} ({cur}/{total})",
    "notify": "[{title}] {text}",
    "drop": {
        "cleared": "[drop] cleared",
        "active": "[drop] {name} — {current}/{required}m",
        "active_full": (
            "[drop] {campaign} ({game})\n"
            "[drop] Drop: {drop_name} ({rewards})\n"
            "[drop] Campaign: {c_bar} {c_pct} ({c_claimed}/{c_total} claimed)\n"
            "[drop] Progress: {d_bar} {d_pct} ({current}/{required}m)"
        ),
    },
    "watch": {
        "watching": "[watch] {channel} ({game})",
        "cleared": "[watch] cleared (was {channel})",
    },
    "ws": {
        "status": "[ws#{idx}] {status}",
        "removed": "[ws#{idx}] removed",
    },
    "login": {
        "status": "[login] {status}",
        "status_id": "[login] {status} (id={id})",
        "header": "Twitch login required (Device Code flow)",
        "step_open": "  1. Open: {url}",
        "step_code": "  2. Enter the code: {code}",
        "step_approve": "  3. Approve the login in your browser, then come back.",
    },
    "commands": {
        "welcome": (
            "Welcome! It looks like this is your first run.\n"
            "Here's how to get started:\n"
            "  1. priority add <game>  — add games to your priority list\n"
            "  2. mode priority_only    — mine only priority-list games\n"
            "  3. resume               — start mining drops\n"
            "  Type 'help' to see all available commands."
        ),
        "help_header": "Commands (type 'help <cmd>' for details):",
        "unknown": "unknown command: {name} (type 'help')",
        "parse_error": "parse error: {exc}",
        "aliases_none": "—",
        "state": "state    : {state}",
        "tray": "tray     : {state}",
        "login": "login    : {status} (user_id={id})",
        "watching": "watching : {channel}",
        "campaigns": "campaigns: {count}, wanted games: {wanted}",
        "channels_count": "channels : {count} known",
        "ws_entry": "  ws#{idx}: {status} ({topics} topics)",
        "ws_none": "  ws: —",
        "bad_number": "bad number: {value}",
        "version": "TwitchDropsMiner {version} (CLI)",
        "about_header": "TwitchDropsMiner-CLI {version}",
        "about_author": "Author: {author}",
        "about_repo": "Repository: {url}",
        "about_sponsor": "Sponsor: {url}",
        "about_how_title": "How It Works",
        "about_how_text": (
            "Every several seconds, the application pretends to watch a particular "
            "stream by fetching stream metadata — this is enough to advance the drops. "
            "Note that this completely bypasses the need to download any actual stream "
            "of video and sound. To keep the status (ONLINE or OFFLINE) of the channels "
            "up-to-date, a websocket connection receives events about streams going up "
            "or down, or updates regarding the current number of viewers."
        ),
        "about_started_title": "Getting Started",
        "about_started_text": (
            "1. Login to the application.\n"
            "2. Ensure your Twitch account is linked to all campaigns you're interested in mining.\n"
            "3. Use 'priority add <game>' to add games to your priority list.\n"
            "4. Use 'mode priority_only' to mine only priority-list games.\n"
            "5. Use 'exclude add <game>' to never mine a specific game.\n"
            "6. Run 'reload' after changing priority/exclude lists for changes to take effect."
        ),
        "about_disclaimer_title": "Disclaimer",
        "about_disclaimer": (
            "1. This tool requires a Twitch login. Your account credentials are stored "
            "locally and are never collected or transmitted.\n"
            "2. Use at your own risk. We are not responsible for any account issues, "
            "including but not limited to bans or suspensions, resulting from the use "
            "of this tool.\n"
            "3. Please verify claimed drops on the Twitch Drops Inventory page.\n"
            "4. Some games may not reliably track watch time due to issues on Twitch's side.\n"
            "5. Closing the tool will stop all mining. Keep it running to continue "
            "earning drops.\n"
            "6. If new campaigns do not appear, try running 'reload' to refresh."
        ),
        "paused": "paused — engine in IDLE",
        "resumed": "resumed — fetching inventory",
        "reloading": "reloading…",
        "watch_usage": "usage: watch <channel-login>",
        "watch_not_found": "channel '{channel}' is not in the known list",
        "watch_hint": "hint: run 'channels' or 'resume' first to populate the list",
        "watch_cant": "can't watch '{channel}' right now (offline / no drops / excluded)",
        "watch_switching": "requested switch to {channel}",
        "unwatch_stopped": "stopped watching",
        "login_hint": (
            "To force a re-login, delete cookies.jar and restart. "
            "Triggering a runtime re-login isn't supported by the engine."
        ),
        "whoami_status": "status : {status}",
        "whoami_user": "user_id: {id}",
        "inv_empty": "inventory is empty (try 'resume' or wait for the next refresh)",
        "inv_no_campaigns": "no campaigns",
        "inv_no_match": "no campaigns match the priority list",
        "inv_no_drop": "no active drop",
        "inv_drop_header": "Game: {game}  Campaign: {campaign}\nDrop: {drop} ({rewards})",
        "inv_drop_campaign": "Campaign progress: {bar} {pct} ({claimed}/{total} claimed)",
        "inv_drop_progress": "Drop progress:     {bar} {pct} ({current}/{required}m)",
        "inv_flag_upcoming": "upcoming",
        "inv_flag_ineligible": "ineligible",
        "inv_flag_active": "active",
        "claimed": "claimed {count} drop(s)",
        "no_channels": "no channels",
        "channels_none_online": "no online channels",
        "ch_online": "online",
        "ch_offline": "offline",
        "saved": "saved",
        "pri_empty": "priority list is empty",
        "pri_already": "already in list: {name}",
        "pri_added": "added: {name}",
        "pri_not_found": "not in list: {name}",
        "pri_removed": "removed: {name}",
        "pri_usage_add": "usage: priority add <game>",
        "pri_usage_remove": "usage: priority remove <game>",
        "pri_usage_move": "usage: priority move <game> <delta>",
        "pri_moved": "moved {name}: {old} -> {new}",
        "pri_delta_bad": "delta must be integer",
        "pri_cleared": "priority list cleared",
        "pri_unknown": "unknown subcommand: {sub}",
        "exc_empty": "exclude list is empty",
        "exc_excluded": "excluded: {name}",
        "exc_unexcluded": "un-excluded: {name}",
        "exc_cleared": "exclude list cleared",
        "exc_unknown": "unknown subcommand: {sub}",
        "exc_usage_add": "usage: exclude add <game>",
        "exc_usage_remove": "usage: exclude remove <game>",
        "mode_current": "{mode}",
        "mode_unknown": "unknown mode: {name}",
        "mode_valid": "valid: {modes}",
        "mode_set": "mode set to {name}",
        "proxy_current": "proxy: {url}",
        "proxy_cleared": "proxy cleared",
        "proxy_set": "proxy set to {url}",
        "lang_current": "lang: {lang}",
        "lang_set": "lang set to {lang} (effective on next start)",
        "lang_list_header": "Available languages (* = current):",
        "lang_list_entry": "  {code:<6} {display}{mark}",
        "quality_current": "quality: {q}",
        "quality_must_be_int": "quality must be an integer 0..2",
        "quality_range": "quality must be 0..2",
        "quality_set": "quality set to {q}",
        "reload_interval_current": "reload interval: {minutes} minutes",
        "reload_interval_must_be_int": "interval must be an integer 10..1440",
        "reload_interval_range": "interval must be 10..1440",
        "reload_interval_set": "reload interval set to {minutes} minutes",
        "get_known_keys": "known keys:",
        "get_unknown_key": "unknown key: {key}",
        "get_value": "{key} = {value}",
        "set_usage": "usage: set <key> <value>",
        "set_unknown_key": "unknown key: {key}",
        "set_cant_parse": "can't parse value: {exc}",
        "set_value": "{key} = {value}",
        "level_current": "level: {level}",
        "level_valid": "valid: {levels}",
        "level_set": "level set to {level}",
        "dump_enabled": "dump enabled",
        "dump_disabled": "dump disabled",
    },
}

default_translation: Translation = {
    "english_name": "English",
    "cli": default_cli_translation,
    "status": {
        "terminated": "\nApplication Terminated.\nClose the window to exit the application.",
        "watching": "Watching: {channel}",
        "goes_online": "{channel} goes ONLINE, switching...",
        "goes_offline": "{channel} goes OFFLINE, switching...",
        "claimed_drop": "Claimed drop: {drop}",
        "no_channel": "No available channels to watch. Waiting for an ONLINE channel...",
        "no_campaign": "No active campaigns to mine drops for. Waiting for an active campaign...",
    },
    "login": {
        "unexpected_content": (
            "Unexpected content type returned, usually due to being redirected. "
            "Do you need to login for internet access?"
        ),
        "error_code": "Login error code: {error_code}",
        "incorrect_login_pass": "Incorrect username or password.",
        "incorrect_email_code": "Incorrect email code.",
        "incorrect_twofa_code": "Incorrect 2FA code.",
        "email_code_required": "Email code required. Check your email.",
        "twofa_code_required": "2FA token required.",
    },
    "error": {
        "captcha": "Your login attempt was denied by CAPTCHA.\nPlease try again in 12+ hours.",
        "site_down": "Twitch is down, retrying in {seconds} seconds...",
        "no_connection": "Cannot connect to Twitch, retrying in {seconds} seconds... ({url})",
    },
    "gui": {
        "status": {
            "idle": "Idle",
            "exiting": "Exiting...",
            "terminated": "Terminated",
            "cleanup": "Cleaning up channels...",
            "gathering": "Gathering channels...",
            "switching": "Switching the channel...",
            "fetching_inventory": "Fetching inventory...",
            "fetching_campaigns": "Fetching campaigns...",
            "adding_campaigns": "Adding campaigns to inventory... {counter}",
        },
        "tray": {
            "notification_title": "Mined Drop",
        },
        "login": {
            "logged_in": "Logged in",
            "logging_in": "Logging in...",
        },
        "websocket": {
            "initializing": "Initializing...",
            "connected": "Connected",
            "disconnected": "Disconnected",
            "connecting": "Connecting...",
            "disconnecting": "Disconnecting...",
            "reconnecting": "Reconnecting...",
        },
        "progress": {
            "name": "Campaign Progress",
            "drop": "Drop:",
            "game": "Game:",
            "campaign": "Campaign:",
            "remaining": "{time} remaining",
            "drop_progress": "Progress:",
            "campaign_progress": "Progress:",
        },
        "channels": {
            "name": "Channels",
            "switch": "Switch",
            "online": "ONLINE  ✔",
            "pending": "OFFLINE ⏳",
            "offline": "OFFLINE ❌",
            "headings": {
                "channel": "Channel",
                "status": "Status",
                "game": "Game",
                "viewers": "Viewers",
            },
        },
        "inventory": {
            "filter": {
                "name": "Filter",
                "not_linked": "Not linked",
                "upcoming": "Upcoming",
                "expired": "Expired",
                "excluded": "Excluded",
                "finished": "Finished",
                "refresh": "Refresh",
            },
            "status": {
                "linked": "Linked ✔",
                "not_linked": "Not Linked ❌",
                "active": "Active ✔",
                "upcoming": "Upcoming ⏳",
                "expired": "Expired ❌",
                "claimed": "Claimed ✔",
                "ready_to_claim": "Ready to claim ⏳",
            },
            "starts": "Starts: {time}",
            "ends": "Ends: {time}",
            "allowed_channels": "Allowed Channels:",
            "all_channels": "All",
            "and_more": "and {amount} more...",
            "percent_progress": "{percent} of {minutes} minutes",
            "minutes_progress": "{minutes} minutes",
        },
        "settings": {
            "general": {
                "name": "General",
                "autostart": "Autostart: ",
                "tray": "Autostart into tray: ",
                "tray_notifications": "Tray notifications: ",
                "dark_mode": "Dark mode: ",
                "priority_mode": "Priority mode: ",
                "proxy": "Proxy (requires restart):",
            },
            "advanced": {
                "name": "Advanced",
                "warning": "Warning!",
                "warning_text": (
                    "These options will cause the miner to misbehave.\n"
                    "If you're experiencing any issues, "
                    "make sure all of these options are disabled."
                ),
                "enable_badges_emotes": "Enable partial support for badges and emotes: ",
                "available_drops_check": "Enable extra available drops check: ",
            },
            "priority_modes": {
                "priority_only": "Priority list only",
                "ending_soonest": "Ending soonest",
                "low_availability": "Low availability first",
            },
            "game_name": "Game name",
            "priority": "Priority",
            "exclude": "Exclude",
            "reload": "Reload",
            "reload_text": "Most changes require a reload to take an immediate effect: ",
        },
        "help": {
            "links": {
                "name": "Useful Links",
                "inventory": "See Twitch inventory",
                "campaigns": "See all campaigns and manage account links",
            },
            "how_it_works": "How It Works",
            "how_it_works_text": (
                "Every several seconds, the application pretends to watch a particular stream "
                "by fetching stream metadata - this is enough to advance the drops. "
                "Note that this completely bypasses the need to download "
                "any actual stream of video and sound. "
                "To keep the status (ONLINE or OFFLINE) of the channels up-to-date, "
                "there's a websocket connection established that receives events about streams "
                "going up or down, or updates regarding the current number of viewers."
            ),
            "getting_started": "Getting Started",
            "getting_started_text": (
                "1. Login to the application.\n"
                "2. Ensure your Twitch account is linked to all campaigns "
                "you're interested in mining.\n"
                "3. If you're interested in mining everything possible, "
                "change the Priority Mode to anything other than \"Priority list only\" "
                "and press on \"Reload\".\n"
                "4. If you want to mine specific games first, use the \"Priority\" list "
                "to set up an ordered list of games of your choice. "
                "Games from the top of the list will be attempted to be mined first, "
                "before the ones lower down the list.\n"
                "5. Keep the \"Priority mode\" selected as \"Priority list only\", "
                "to avoid mining games that are not on the priority list. "
                "Or not - it's up to you.\n"
                "6. Use the \"Exclude\" list to tell the application "
                "which games should never be mined.\n"
                "7. Changing the contents of either of the lists, or changing "
                "the \"Priority mode\", requires you to press on \"Reload\" "
                "for the changes to take an effect."
            ),
        },
    },
}

# Backward compatible aliases: old full language names → ISO 639-1 codes
_LANG_ALIASES: dict[str, str] = {
    "English": "en", "Čeština": "cs", "Czech": "cs",
    "Dansk": "da", "Danish": "da",
    "Deutsch": "de", "German": "de",
    "Español": "es", "Spanish": "es",
    "Français": "fr", "French": "fr",
    "Indonesian": "id",
    "Italiano": "it", "Italian": "it",
    "Nederlandse": "nl", "Dutch": "nl",
    "Norsk": "no", "Norwegian": "no",
    "Polski": "pl", "Polish": "pl",
    "Português": "pt", "Portuguese": "pt",
    "Română": "ro", "Romanian": "ro",
    "Türkçe": "tr", "Turkish": "tr",
    "Русский": "ru", "Russian": "ru",
    "Українська": "uk", "Ukrainian": "uk",
    "العربية": "ar", "Arabic": "ar",
    "日本語": "ja", "Japanese": "ja",
    "简体中文": "zh-CN", "Simplified Chinese": "zh-CN",
    "繁體中文": "zh-TW", "Traditional Chinese": "zh-TW",
}

# ISO code → display name (populated at init from file english_name fields)
_LANG_DISPLAY: dict[str, str] = {}

class Translator:
    def __init__(self) -> None:
        self._langs: list[str] = []
        # start with (and always copy) the default translation
        self._translation: Translation = default_translation.copy()
        # if we're in dev, update the template English.json file
        if not IS_PACKAGED:
            default_langpath = LANG_PATH.joinpath(f"{DEFAULT_LANG}.json")
            json_save(default_langpath, default_translation)
        self._translation["language_name"] = DEFAULT_LANG
        # load available translation names
        self._lang_names: dict[str, str] = {}
        for filepath in LANG_PATH.glob("*.json"):
            code = filepath.stem
            self._langs.append(code)
            if code not in _LANG_DISPLAY:
                # extract english_name from the file itself
                try:
                    data = json_load(filepath, {}, merge=False)
                    display = data.get("english_name", code)
                except Exception:
                    display = code
                _LANG_DISPLAY[code] = display
            self._lang_names[code] = _LANG_DISPLAY.get(code, code)
        self._langs.sort()
        if DEFAULT_LANG in self._langs:
            self._langs.remove(DEFAULT_LANG)
        self._langs.insert(0, DEFAULT_LANG)
        # ensure default lang has a display name
        if DEFAULT_LANG not in self._lang_names:
            self._lang_names[DEFAULT_LANG] = "English"

    def language_display(self, code: str) -> str:
        """Return the English display name for a language code."""
        return self._lang_names.get(code, code)

    @property
    def languages(self) -> abc.Iterable[str]:
        return iter(self._langs)

    @property
    def languages_display(self) -> abc.Iterable[str]:
        """Return display names in the same order as `languages`."""
        for code in self._langs:
            yield self.language_display(code)

    @property
    def current(self) -> str:
        return self._translation["language_name"]

    def set_language(self, language: str):
        # Resolve old full-name aliases to ISO codes
        language = _LANG_ALIASES.get(language, language)
        if language not in self._langs:
            raise ValueError("Unrecognized language")
        elif self._translation["language_name"] == language:
            # same language as loaded selected
            return
        elif language == DEFAULT_LANG:
            # default language selected - use the memory value
            self._translation = default_translation.copy()
        else:
            self._translation = json_load(
                LANG_PATH.joinpath(f"{language}.json"), default_translation
            )
            if "language_name" in self._translation:
                raise ValueError("Translations cannot define 'language_name'")
        self._translation["language_name"] = language

    def __call__(self, *path: str) -> str:
        if not path:
            raise ValueError("Language path expected")
        v: Any = self._translation
        try:
            for key in path:
                v = v[key]
        except KeyError:
            # this can only really happen for the default translation
            raise MinerException(
                f"{self.current} translation is missing the '{' -> '.join(path)}' translation key"
            )
        return v

_ = Translator()
