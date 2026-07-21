"""
CommandRegistry — interactive shell command dispatcher for the CLI.

Each command is a small async function that receives:

    ctx: CommandContext  (twitch, cli, args, raw)

The dispatcher is shlex-based, so quoted arguments work as expected.
"""

from __future__ import annotations

import logging
import shlex
import sys
from collections import abc
from dataclasses import dataclass
from typing import TYPE_CHECKING, Awaitable, Callable

from yarl import URL

from constants import State, PriorityMode
from exceptions import ExitRequest, ReloadRequest
from translate import _

if TYPE_CHECKING:
    from twitch import Twitch
    from cli import CLIManager


logger = logging.getLogger("TwitchDrops")


@dataclass
class CommandContext:
    twitch: Twitch
    cli: CLIManager
    args: list[str]
    raw: str


CommandFn = Callable[[CommandContext], Awaitable[None]]


@dataclass
class Command:
    name: str
    summary: str
    run: CommandFn
    aliases: tuple[str, ...] = ()
    usage: str = ""

    @property
    def all_names(self) -> tuple[str, ...]:
        return (self.name, *self.aliases)


class CommandRegistry:
    def __init__(self, twitch: Twitch, cli: CLIManager) -> None:
        self._twitch = twitch
        self._cli = cli
        self._commands: dict[str, Command] = {}
        self._register_builtins()

    # ----- registry --------------------------------------------------------

    def add(self, command: Command) -> None:
        for name in command.all_names:
            self._commands[name] = command

    def find(self, name: str) -> Command | None:
        return self._commands.get(name)

    def all(self) -> list[Command]:
        # Deduplicated by identity
        seen: set[int] = set()
        out: list[Command] = []
        for c in self._commands.values():
            if id(c) in seen:
                continue
            seen.add(id(c))
            out.append(c)
        return sorted(out, key=lambda c: c.name)

    async def dispatch(self, line: str) -> None:
        try:
            tokens = shlex.split(line)
        except ValueError as exc:
            self._cli.print(_("cli", "commands", "parse_error").format(exc=exc))
            return
        if not tokens:
            return
        name, *args = tokens
        cmd = self.find(name.lower())
        if cmd is None:
            self._cli.print(_("cli", "commands", "unknown").format(name=name))
            return
        ctx = CommandContext(self._twitch, self._cli, args, line)
        await cmd.run(ctx)

    # ----- built-ins -------------------------------------------------------

    def _register_builtins(self) -> None:
        # Register from a list to keep the file readable
        defs: list[Command] = [
            Command("help", "List commands or show help for one", _cmd_help, ("?",), "help [cmd]"),
            Command("exit", "Quit the application", _cmd_exit, ("quit", "q")),
            Command("status", "Show current state, watch target, websockets", _cmd_status),
            Command("log", "Print the last N output lines (default 20)", _cmd_log, usage="log [N]"),
            Command("clear", "Clear the screen", _cmd_clear),
            Command("version", "Show the running version", _cmd_version),

            Command("login", "Force a fresh OAuth device-code login", _cmd_login),
            Command("whoami", "Show the logged-in Twitch user id", _cmd_whoami),

            Command("pause", "Pause mining (drop into IDLE)", _cmd_pause),
            Command("resume", "Resume mining (re-fetch inventory)", _cmd_resume),
            Command("reload", "Reload the entire client", _cmd_reload),

            Command(
                "watch",
                "Watch the given channel by login",
                _cmd_watch,
                usage="watch <channel-login>",
            ),
            Command("unwatch", "Stop watching the current channel", _cmd_unwatch),

            Command("inventory", "List campaigns and drop progress", _cmd_inventory, ("inv",)),
            Command("campaigns", "List campaigns only", _cmd_campaigns),
            Command("drops", "Show progress on the active drop", _cmd_drops),
            Command("claim", "Force-claim any pending drops", _cmd_claim),

            Command(
                "channels",
                "List known channels (online first)",
                _cmd_channels,
                usage="channels [--all]",
            ),
            Command("online", "List only online channels", _cmd_online),

            Command(
                "priority",
                "Manage priority list",
                _cmd_priority,
                usage="priority list|add <game>|remove <game>|move <game> <delta>|clear",
            ),
            Command(
                "exclude",
                "Manage excluded games",
                _cmd_exclude,
                usage="exclude list|add <game>|remove <game>|clear",
            ),
            Command(
                "mode",
                "Get/set priority mode",
                _cmd_mode,
                usage="mode [priority_only|ending_soonest|low_avbl_first]",
            ),
            Command("proxy", "Show or set the HTTP proxy", _cmd_proxy, usage="proxy [<url>|clear]"),
            Command(
                "lang",
                "Show or list languages, or set the current language",
                _cmd_lang,
                usage="lang [-ls | --list] | lang <code>",
            ),
            Command(
                "quality",
                "Show or set the connection quality (0=lowest..2=highest)",
                _cmd_quality,
                usage="quality [0|1|2]",
            ),
            Command(
                "reload-interval",
                "Show or set inventory reload interval in minutes",
                _cmd_reload_interval,
                ("interval",),
                usage="reload-interval [<minutes>]",
            ),
            Command("get", "Print a setting value", _cmd_get, usage="get <key>"),
            Command("set", "Update a setting value", _cmd_set, usage="set <key> <value>"),
            Command("save", "Persist settings to disk now", _cmd_save),

            Command("level", "Set log level (DEBUG/INFO/WARNING/ERROR/CRITICAL)", _cmd_level),
            Command("dump", "Toggle GQL response dump", _cmd_dump),
        ]
        for d in defs:
            self.add(d)


# ---------------------------------------------------------------------------
# Command implementations
# ---------------------------------------------------------------------------

# General -------------------------------------------------------------------

async def _cmd_help(ctx: CommandContext) -> None:
    registry: CommandRegistry | None = getattr(ctx.cli, "_registry", None)
    if registry is None:
        registry = CommandRegistry(ctx.twitch, ctx.cli)
    if ctx.args:
        target = ctx.args[0].lower()
        cmd = registry.find(target)
        if cmd is None:
            ctx.cli.print(_("cli", "commands", "unknown").format(name=target))
            return
        aliases = ", ".join(cmd.aliases) or _("cli", "commands", "aliases_none")
        ctx.cli.print(f"{cmd.name}  —  {cmd.summary}")
        if cmd.usage:
            ctx.cli.print(f"  usage:   {cmd.usage}")
        ctx.cli.print(f"  aliases: {aliases}")
        return
    ctx.cli.print(_("cli", "commands", "help_header"))
    for cmd in registry.all():
        ctx.cli.print(f"  {cmd.name:<10}  {cmd.summary}")


async def _cmd_exit(ctx: CommandContext) -> None:
    raise ExitRequest()


async def _cmd_status(ctx: CommandContext) -> None:
    t = ctx.twitch
    cli = ctx.cli
    state_name = t._state.name if hasattr(t, "_state") else "?"
    cli.print(_("cli", "commands", "state").format(state=state_name))
    cli.print(_("cli", "commands", "tray").format(state=cli.tray.state))
    cli.print(_("cli", "commands", "login").format(status=cli.login.status, id=cli.login.user_id))
    watching = t.watching_channel.get_with_default(None)
    none = _("cli", "commands", "aliases_none")
    cli.print(_("cli", "commands", "watching").format(channel=(watching.name if watching else none)))
    cli.print(_("cli", "commands", "campaigns").format(count=len(t.inventory), wanted=len(t.wanted_games)))
    cli.print(_("cli", "commands", "channels_count").format(count=len(t.channels)))
    if cli.websockets.entries:
        for e in cli.websockets.entries:
            cli.print(_("cli", "commands", "ws_entry").format(idx=e.idx, status=e.status, topics=e.topics))
    else:
        cli.print(_("cli", "commands", "ws_none"))


async def _cmd_log(ctx: CommandContext) -> None:
    n = 20
    if ctx.args:
        try:
            n = max(1, int(ctx.args[0]))
        except ValueError:
            ctx.cli.print(_("cli", "commands", "bad_number").format(value=ctx.args[0]))
            return
    lines = ctx.cli.output_buffer[-n:]
    for line in lines:
        sys.stdout.write(line + "\n")
    sys.stdout.flush()


async def _cmd_clear(ctx: CommandContext) -> None:
    ctx.cli.clear_screen()


async def _cmd_version(ctx: CommandContext) -> None:
    from version import __version__
    ctx.cli.print(_("cli", "commands", "version").format(version=__version__))


# Login ---------------------------------------------------------------------

async def _cmd_login(ctx: CommandContext) -> None:
    ctx.cli.print(_("cli", "commands", "login_hint"))


async def _cmd_whoami(ctx: CommandContext) -> None:
    cli = ctx.cli
    cli.print(_("cli", "commands", "whoami_status").format(status=cli.login.status))
    cli.print(_("cli", "commands", "whoami_user").format(id=cli.login.user_id))


# Mining control ------------------------------------------------------------

async def _cmd_pause(ctx: CommandContext) -> None:
    ctx.twitch.stop_watching()
    ctx.twitch.change_state(State.IDLE)
    ctx.cli.print(_("cli", "commands", "paused"))


async def _cmd_resume(ctx: CommandContext) -> None:
    ctx.twitch.change_state(State.INVENTORY_FETCH)
    ctx.cli.print(_("cli", "commands", "resumed"))


async def _cmd_reload(ctx: CommandContext) -> None:
    ctx.cli.print(_("cli", "commands", "reloading"))
    raise ReloadRequest()


async def _cmd_watch(ctx: CommandContext) -> None:
    if not ctx.args:
        ctx.cli.print(_("cli", "commands", "watch_usage"))
        return
    target = ctx.args[0].lower().lstrip("@")
    found = None
    for ch in ctx.twitch.channels.values():
        if ch.name.lower() == target or getattr(ch, "_login", "").lower() == target:
            found = ch
            break
    if found is None:
        ctx.cli.print(_("cli", "commands", "watch_not_found").format(channel=target))
        ctx.cli.print(_("cli", "commands", "watch_hint"))
        return
    if not ctx.twitch.can_watch(found):
        ctx.cli.print(_("cli", "commands", "watch_cant").format(channel=found.name))
        return
    ctx.cli.channels.request(found)
    ctx.twitch.change_state(State.CHANNEL_SWITCH)
    ctx.cli.print(_("cli", "commands", "watch_switching").format(channel=found.name))


async def _cmd_unwatch(ctx: CommandContext) -> None:
    ctx.twitch.stop_watching()
    ctx.cli.print(_("cli", "commands", "unwatch_stopped"))


# Inventory -----------------------------------------------------------------

async def _cmd_inventory(ctx: CommandContext) -> None:
    inv = ctx.twitch.inventory
    if not inv:
        ctx.cli.print(_("cli", "commands", "inv_empty"))
        return
    bar_w = 16
    for camp in inv:
        flags = []
        if getattr(camp, "upcoming", False):
            flags.append(_("cli", "commands", "inv_flag_upcoming"))
        if not getattr(camp, "eligible", True):
            flags.append(_("cli", "commands", "inv_flag_ineligible"))
        if getattr(camp, "active", False):
            flags.append(_("cli", "commands", "inv_flag_active"))
        flag_str = (" [" + ", ".join(flags) + "]") if flags else ""
        c_bar = ctx.cli._render_bar(camp.progress, bar_w) if camp.total_drops > 0 else ""
        ctx.cli.print(f"• {camp.game.name}: {camp.name}{flag_str}")
        if c_bar:
            ctx.cli.print(f"  Campaign: {c_bar} ({camp.claimed_drops}/{camp.total_drops} claimed)")
        for drop in getattr(camp, "drops", []):
            done = "✓" if getattr(drop, "is_claimed", False) else " "
            try:
                cur = drop.current_minutes
                req = drop.required_minutes
            except Exception:
                cur = req = 0
            d_bar = ctx.cli._render_bar(drop.progress, 12) if req > 0 else ""
            bar_str = f"  {d_bar}" if d_bar else ""
            ctx.cli.print(f"    [{done}] {drop.name}  {cur}/{req}m{bar_str}")


async def _cmd_campaigns(ctx: CommandContext) -> None:
    inv = ctx.twitch.inventory
    if not inv:
        ctx.cli.print(_("cli", "commands", "inv_no_campaigns"))
        return
    for camp in inv:
        ctx.cli.print(f"• {camp.game.name}: {camp.name}")


async def _cmd_drops(ctx: CommandContext) -> None:
    drop = ctx.cli.progress.current
    if drop is None:
        ctx.cli.print(_("cli", "commands", "inv_no_drop"))
        return
    campaign = drop.campaign
    bar_w = 25
    c_bar = ctx.cli._render_bar(campaign.progress, bar_w)
    d_bar = ctx.cli._render_bar(drop.progress, bar_w)
    ctx.cli.print(_("cli", "commands", "inv_drop_header").format(
        game=campaign.game.name,
        campaign=campaign.name,
        drop=drop.name,
        rewards=drop.rewards_text(),
    ))
    ctx.cli.print(_("cli", "commands", "inv_drop_campaign").format(
        bar=c_bar,
        pct=f"{campaign.progress:.0%}",
        claimed=campaign.claimed_drops,
        total=campaign.total_drops,
    ))
    ctx.cli.print(_("cli", "commands", "inv_drop_progress").format(
        bar=d_bar,
        pct=f"{drop.progress:.0%}",
        current=drop.current_minutes,
        required=drop.required_minutes,
    ))


async def _cmd_claim(ctx: CommandContext) -> None:
    claimed = 0
    for camp in ctx.twitch.inventory:
        if getattr(camp, "upcoming", False):
            continue
        for drop in getattr(camp, "drops", []):
            if getattr(drop, "can_claim", False):
                ok = await drop.claim()
                if ok:
                    claimed += 1
    ctx.cli.print(_("cli", "commands", "claimed").format(count=claimed))


# Channels ------------------------------------------------------------------

async def _cmd_channels(ctx: CommandContext) -> None:
    show_all = "--all" in ctx.args
    chans = list(ctx.twitch.channels.values())
    if not chans:
        ctx.cli.print(_("cli", "commands", "no_channels"))
        return
    chans.sort(key=lambda c: (c.offline, c.name.lower()))
    for ch in chans:
        if not show_all and ch.offline:
            continue
        game = ch.game.name if ch.game else "—"
        flags = _("cli", "commands", "ch_online") if not ch.offline else _("cli", "commands", "ch_offline")
        viewers = getattr(ch, "viewers", None)
        v = f", {viewers} viewers" if viewers is not None and not ch.offline else ""
        ctx.cli.print(f"  {ch.name:<25} {flags:<8} {game}{v}")


async def _cmd_online(ctx: CommandContext) -> None:
    ctx.args.append("--online-only")
    chans = [c for c in ctx.twitch.channels.values() if not c.offline]
    if not chans:
        ctx.cli.print(_("cli", "commands", "channels_none_online"))
        return
    for ch in sorted(chans, key=lambda c: c.name.lower()):
        game = ch.game.name if ch.game else "—"
        ctx.cli.print(f"  {ch.name:<25} {game}")


# Settings ------------------------------------------------------------------

def _settings(ctx: CommandContext):
    return ctx.twitch.settings


async def _cmd_priority(ctx: CommandContext) -> None:
    if not ctx.args:
        ctx.args = ["list"]
    sub = ctx.args[0].lower()
    s = _settings(ctx)
    pri: list[str] = list(s.priority)
    if sub == "list":
        if not pri:
            ctx.cli.print(_("cli", "commands", "pri_empty"))
            return
        for i, name in enumerate(pri):
            ctx.cli.print(f"  {i}: {name}")
        return
    if sub == "add":
        if len(ctx.args) < 2:
            ctx.cli.print(_("cli", "commands", "pri_usage_add"))
            return
        name = " ".join(ctx.args[1:])
        if name in pri:
            ctx.cli.print(_("cli", "commands", "pri_already").format(name=name))
            return
        pri.append(name)
        s.priority = pri
        s.save()
        ctx.cli.print(_("cli", "commands", "pri_added").format(name=name))
        return
    if sub == "remove":
        if len(ctx.args) < 2:
            ctx.cli.print(_("cli", "commands", "pri_usage_remove"))
            return
        name = " ".join(ctx.args[1:])
        if name not in pri:
            ctx.cli.print(_("cli", "commands", "pri_not_found").format(name=name))
            return
        pri.remove(name)
        s.priority = pri
        s.save()
        ctx.cli.print(_("cli", "commands", "pri_removed").format(name=name))
        return
    if sub == "move":
        if len(ctx.args) < 3:
            ctx.cli.print(_("cli", "commands", "pri_usage_move"))
            return
        name = ctx.args[1]
        try:
            delta = int(ctx.args[2])
        except ValueError:
            ctx.cli.print(_("cli", "commands", "pri_delta_bad"))
            return
        if name not in pri:
            ctx.cli.print(_("cli", "commands", "pri_not_found").format(name=name))
            return
        idx = pri.index(name)
        new_idx = max(0, min(len(pri) - 1, idx + delta))
        pri.insert(new_idx, pri.pop(idx))
        s.priority = pri
        s.save()
        ctx.cli.print(_("cli", "commands", "pri_moved").format(name=name, old=idx, new=new_idx))
        return
    if sub == "clear":
        s.priority = []
        s.save()
        ctx.cli.print(_("cli", "commands", "pri_cleared"))
        return
    ctx.cli.print(_("cli", "commands", "pri_unknown").format(sub=sub))


async def _cmd_exclude(ctx: CommandContext) -> None:
    if not ctx.args:
        ctx.args = ["list"]
    sub = ctx.args[0].lower()
    s = _settings(ctx)
    excl: set[str] = set(s.exclude)
    if sub == "list":
        if not excl:
            ctx.cli.print(_("cli", "commands", "exc_empty"))
            return
        for name in sorted(excl):
            ctx.cli.print(f"  {name}")
        return
    if sub == "add":
        if len(ctx.args) < 2:
            ctx.cli.print(_("cli", "commands", "exc_usage_add"))
            return
        name = " ".join(ctx.args[1:])
        excl.add(name)
        s.exclude = excl
        s.save()
        ctx.cli.print(_("cli", "commands", "exc_excluded").format(name=name))
        return
    if sub == "remove":
        if len(ctx.args) < 2:
            ctx.cli.print(_("cli", "commands", "exc_usage_remove"))
            return
        name = " ".join(ctx.args[1:])
        excl.discard(name)
        s.exclude = excl
        s.save()
        ctx.cli.print(_("cli", "commands", "exc_unexcluded").format(name=name))
        return
    if sub == "clear":
        s.exclude = set()
        s.save()
        ctx.cli.print(_("cli", "commands", "exc_cleared"))
        return
    ctx.cli.print(_("cli", "commands", "exc_unknown").format(sub=sub))


_MODE_NAMES = {
    "priority_only": PriorityMode.PRIORITY_ONLY,
    "ending_soonest": PriorityMode.ENDING_SOONEST,
    "low_avbl_first": PriorityMode.LOW_AVBL_FIRST,
}


async def _cmd_mode(ctx: CommandContext) -> None:
    s = _settings(ctx)
    if not ctx.args:
        for k, v in _MODE_NAMES.items():
            mark = " *" if s.priority_mode is v else ""
            ctx.cli.print(f"  {k}{mark}")
        return
    name = ctx.args[0].lower()
    if name not in _MODE_NAMES:
        ctx.cli.print(_("cli", "commands", "mode_unknown").format(name=name))
        ctx.cli.print(_("cli", "commands", "mode_valid").format(modes=", ".join(_MODE_NAMES)))
        return
    s.priority_mode = _MODE_NAMES[name]
    s.save()
    ctx.cli.print(_("cli", "commands", "mode_set").format(name=name))


async def _cmd_proxy(ctx: CommandContext) -> None:
    s = _settings(ctx)
    if not ctx.args:
        none = _("cli", "commands", "aliases_none")
        ctx.cli.print(_("cli", "commands", "proxy_current").format(url=(s.proxy or none)))
        return
    val = ctx.args[0]
    if val.lower() == "clear":
        s.proxy = URL()
        s.save()
        ctx.cli.print(_("cli", "commands", "proxy_cleared"))
        return
    s.proxy = URL(val)
    s.save()
    ctx.cli.print(_("cli", "commands", "proxy_set").format(url=s.proxy))


async def _cmd_lang(ctx: CommandContext) -> None:
    s = _settings(ctx)
    if not ctx.args:
        ctx.cli.print(_("cli", "commands", "lang_current").format(lang=s.language))
        return
    if ctx.args[0] in ("-ls", "--list"):
        ctx.cli.print(_("cli", "commands", "lang_list_header"))
        for code in _.languages:
            display = _.language_display(code)
            mark = " *" if code == s.language else ""
            ctx.cli.print(
                _("cli", "commands", "lang_list_entry").format(code=code, display=display, mark=mark)
            )
        return
    s.language = ctx.args[0]
    s.save()
    ctx.cli.print(_("cli", "commands", "lang_set").format(lang=s.language))


async def _cmd_quality(ctx: CommandContext) -> None:
    s = _settings(ctx)
    if not ctx.args:
        ctx.cli.print(_("cli", "commands", "quality_current").format(q=s.connection_quality))
        return
    try:
        q = int(ctx.args[0])
    except ValueError:
        ctx.cli.print(_("cli", "commands", "quality_must_be_int"))
        return
    if not 0 <= q <= 2:
        ctx.cli.print(_("cli", "commands", "quality_range"))
        return
    s.connection_quality = q
    s.save()
    ctx.cli.print(_("cli", "commands", "quality_set").format(q=q))


async def _cmd_reload_interval(ctx: CommandContext) -> None:
    s = _settings(ctx)
    if not ctx.args:
        ctx.cli.print(_("cli", "commands", "reload_interval_current").format(minutes=s.reload_interval))
        return
    try:
        minutes = int(ctx.args[0])
    except ValueError:
        ctx.cli.print(_("cli", "commands", "reload_interval_must_be_int"))
        return
    if not 10 <= minutes <= 1440:
        ctx.cli.print(_("cli", "commands", "reload_interval_range"))
        return
    s.reload_interval = minutes
    s.save()
    ctx.cli.print(_("cli", "commands", "reload_interval_set").format(minutes=minutes))


_GETTABLE_KEYS = (
    "priority", "exclude", "priority_mode", "language", "proxy",
    "connection_quality", "reload_interval", "tray_notifications",
    "enable_badges_emotes", "available_drops_check", "dark_mode", "autostart_tray",
)


async def _cmd_get(ctx: CommandContext) -> None:
    if not ctx.args:
        ctx.cli.print(_("cli", "commands", "get_known_keys"))
        for k in _GETTABLE_KEYS:
            ctx.cli.print(f"  {k}")
        return
    key = ctx.args[0]
    s = _settings(ctx)
    if key not in s._settings:
        ctx.cli.print(_("cli", "commands", "get_unknown_key").format(key=key))
        return
    val = getattr(s, key)
    if isinstance(val, PriorityMode):
        val = val.name.lower()
    ctx.cli.print(_("cli", "commands", "get_value").format(key=key, value=val))


async def _cmd_set(ctx: CommandContext) -> None:
    if len(ctx.args) < 2:
        ctx.cli.print(_("cli", "commands", "set_usage"))
        return
    key, raw = ctx.args[0], " ".join(ctx.args[1:])
    s = _settings(ctx)
    if key not in s._settings:
        ctx.cli.print(_("cli", "commands", "set_unknown_key").format(key=key))
        return
    cur = getattr(s, key)
    try:
        if isinstance(cur, bool):
            v: object = raw.lower() in ("1", "true", "yes", "on")
        elif isinstance(cur, int):
            v = int(raw)
        elif isinstance(cur, URL):
            v = URL(raw)
        elif isinstance(cur, set):
            v = set(part for part in raw.split(",") if part)
        elif isinstance(cur, list):
            v = [part for part in raw.split(",") if part]
        elif isinstance(cur, PriorityMode):
            if raw not in _MODE_NAMES:
                ctx.cli.print(_("cli", "commands", "mode_valid").format(modes=", ".join(_MODE_NAMES)))
                return
            v = _MODE_NAMES[raw]
        else:
            v = raw
    except Exception as exc:
        ctx.cli.print(_("cli", "commands", "set_cant_parse").format(exc=exc))
        return
    setattr(s, key, v)
    s.save()
    ctx.cli.print(_("cli", "commands", "set_value").format(key=key, value=getattr(s, key)))


async def _cmd_save(ctx: CommandContext) -> None:
    ctx.twitch.save(force=True)
    ctx.cli.print(_("cli", "commands", "saved"))


# Debug ---------------------------------------------------------------------

_LEVEL_BY_NAME = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


async def _cmd_level(ctx: CommandContext) -> None:
    log = logging.getLogger("TwitchDrops")
    if not ctx.args:
        ctx.cli.print(_("cli", "commands", "level_current").format(level=logging.getLevelName(log.getEffectiveLevel())))
        return
    name = ctx.args[0].upper()
    if name not in _LEVEL_BY_NAME:
        ctx.cli.print(_("cli", "commands", "level_valid").format(levels=", ".join(_LEVEL_BY_NAME)))
        return
    log.setLevel(_LEVEL_BY_NAME[name])
    ctx.cli.print(_("cli", "commands", "level_set").format(level=name))


async def _cmd_dump(ctx: CommandContext) -> None:
    s = _settings(ctx)
    cur = getattr(s._args, "dump", False)
    new = not cur if not ctx.args else ctx.args[0].lower() in ("1", "true", "on", "yes")
    s._args.dump = new
    ctx.cli.print(_("cli", "commands", "dump_enabled") if new else _("cli", "commands", "dump_disabled"))
