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
            self._cli.print(f"parse error: {exc}")
            return
        if not tokens:
            return
        name, *args = tokens
        cmd = self.find(name.lower())
        if cmd is None:
            self._cli.print(f"unknown command: {name} (type 'help')")
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
            Command("lang", "Show or set the language", _cmd_lang, usage="lang [code]"),
            Command(
                "quality",
                "Show or set the connection quality (0=lowest..2=highest)",
                _cmd_quality,
                usage="quality [0|1|2]",
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
            ctx.cli.print(f"unknown command: {target}")
            return
        aliases = ", ".join(cmd.aliases) or "—"
        ctx.cli.print(f"{cmd.name}  —  {cmd.summary}")
        if cmd.usage:
            ctx.cli.print(f"  usage:   {cmd.usage}")
        ctx.cli.print(f"  aliases: {aliases}")
        return
    ctx.cli.print("Commands (type 'help <cmd>' for details):")
    for cmd in registry.all():
        ctx.cli.print(f"  {cmd.name:<10}  {cmd.summary}")


async def _cmd_exit(ctx: CommandContext) -> None:
    raise ExitRequest()


async def _cmd_status(ctx: CommandContext) -> None:
    t = ctx.twitch
    cli = ctx.cli
    state_name = t._state.name if hasattr(t, "_state") else "?"
    cli.print(f"state    : {state_name}")
    cli.print(f"tray     : {cli.tray.state}")
    cli.print(f"login    : {cli.login.status} (user_id={cli.login.user_id})")
    watching = t.watching_channel.get_with_default(None)
    cli.print(f"watching : {watching.name if watching else '—'}")
    cli.print(f"campaigns: {len(t.inventory)}, wanted games: {len(t.wanted_games)}")
    cli.print(f"channels : {len(t.channels)} known")
    if cli.websockets.entries:
        for e in cli.websockets.entries:
            cli.print(f"  ws#{e.idx}: {e.status} ({e.topics} topics)")
    else:
        cli.print("  ws: —")


async def _cmd_log(ctx: CommandContext) -> None:
    n = 20
    if ctx.args:
        try:
            n = max(1, int(ctx.args[0]))
        except ValueError:
            ctx.cli.print(f"bad number: {ctx.args[0]}")
            return
    lines = ctx.cli.output_buffer[-n:]
    for line in lines:
        sys.stdout.write(line + "\n")
    sys.stdout.flush()


async def _cmd_clear(ctx: CommandContext) -> None:
    sys.stdout.write("\x1b[2J\x1b[H")
    sys.stdout.flush()


async def _cmd_version(ctx: CommandContext) -> None:
    from version import __version__
    ctx.cli.print(f"TwitchDropsMiner v{__version__} (CLI)")


# Login ---------------------------------------------------------------------

async def _cmd_login(ctx: CommandContext) -> None:
    ctx.cli.print(
        "To force a re-login, delete cookies.jar and restart. "
        "Triggering a runtime re-login isn't supported by the engine."
    )


async def _cmd_whoami(ctx: CommandContext) -> None:
    cli = ctx.cli
    cli.print(f"status : {cli.login.status}")
    cli.print(f"user_id: {cli.login.user_id}")


# Mining control ------------------------------------------------------------

async def _cmd_pause(ctx: CommandContext) -> None:
    ctx.twitch.stop_watching()
    ctx.twitch.change_state(State.IDLE)
    ctx.cli.print("paused — engine in IDLE")


async def _cmd_resume(ctx: CommandContext) -> None:
    ctx.twitch.change_state(State.INVENTORY_FETCH)
    ctx.cli.print("resumed — fetching inventory")


async def _cmd_reload(ctx: CommandContext) -> None:
    ctx.cli.print("reloading…")
    raise ReloadRequest()


async def _cmd_watch(ctx: CommandContext) -> None:
    if not ctx.args:
        ctx.cli.print("usage: watch <channel-login>")
        return
    target = ctx.args[0].lower().lstrip("@")
    found = None
    for ch in ctx.twitch.channels.values():
        if ch.name.lower() == target or getattr(ch, "_login", "").lower() == target:
            found = ch
            break
    if found is None:
        ctx.cli.print(f"channel '{target}' is not in the known list")
        ctx.cli.print("hint: run 'channels' or 'resume' first to populate the list")
        return
    if not ctx.twitch.can_watch(found):
        ctx.cli.print(f"can't watch '{found.name}' right now (offline / no drops / excluded)")
        return
    ctx.cli.channels.request(found)
    ctx.twitch.change_state(State.CHANNEL_SWITCH)
    ctx.cli.print(f"requested switch to {found.name}")


async def _cmd_unwatch(ctx: CommandContext) -> None:
    ctx.twitch.stop_watching()
    ctx.cli.print("stopped watching")


# Inventory -----------------------------------------------------------------

async def _cmd_inventory(ctx: CommandContext) -> None:
    inv = ctx.twitch.inventory
    if not inv:
        ctx.cli.print("inventory is empty (try 'resume' or wait for the next refresh)")
        return
    for camp in inv:
        flags = []
        if getattr(camp, "upcoming", False):
            flags.append("upcoming")
        if not getattr(camp, "eligible", True):
            flags.append("ineligible")
        if getattr(camp, "active", False):
            flags.append("active")
        flag_str = (" [" + ", ".join(flags) + "]") if flags else ""
        ctx.cli.print(f"• {camp.game.name}: {camp.name}{flag_str}")
        for drop in getattr(camp, "drops", []):
            done = "✓" if getattr(drop, "is_claimed", False) else " "
            try:
                cur = drop.current_minutes
                req = drop.required_minutes
            except Exception:
                cur = req = 0
            ctx.cli.print(f"    [{done}] {drop.name}  {cur}/{req}m")


async def _cmd_campaigns(ctx: CommandContext) -> None:
    inv = ctx.twitch.inventory
    if not inv:
        ctx.cli.print("no campaigns")
        return
    for camp in inv:
        ctx.cli.print(f"• {camp.game.name}: {camp.name}")


async def _cmd_drops(ctx: CommandContext) -> None:
    drop = ctx.cli.progress.current
    if drop is None:
        ctx.cli.print("no active drop")
        return
    ctx.cli.print(
        f"{drop.name} — {drop.current_minutes}/{drop.required_minutes}m"
    )


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
    ctx.cli.print(f"claimed {claimed} drop(s)")


# Channels ------------------------------------------------------------------

async def _cmd_channels(ctx: CommandContext) -> None:
    show_all = "--all" in ctx.args
    chans = list(ctx.twitch.channels.values())
    if not chans:
        ctx.cli.print("no channels")
        return
    chans.sort(key=lambda c: (c.offline, c.name.lower()))
    for ch in chans:
        if not show_all and ch.offline:
            continue
        game = ch.game.name if ch.game else "—"
        flags = "online" if not ch.offline else "offline"
        viewers = getattr(ch, "viewers", None)
        v = f", {viewers} viewers" if viewers is not None and not ch.offline else ""
        ctx.cli.print(f"  {ch.name:<25} {flags:<8} {game}{v}")


async def _cmd_online(ctx: CommandContext) -> None:
    ctx.args.append("--online-only")
    chans = [c for c in ctx.twitch.channels.values() if not c.offline]
    if not chans:
        ctx.cli.print("no online channels")
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
            ctx.cli.print("priority list is empty")
            return
        for i, name in enumerate(pri):
            ctx.cli.print(f"  {i}: {name}")
        return
    if sub == "add":
        if len(ctx.args) < 2:
            ctx.cli.print("usage: priority add <game>")
            return
        name = " ".join(ctx.args[1:])
        if name in pri:
            ctx.cli.print(f"already in list: {name}")
            return
        pri.append(name)
        s.priority = pri
        s.save()
        ctx.cli.print(f"added: {name}")
        return
    if sub == "remove":
        if len(ctx.args) < 2:
            ctx.cli.print("usage: priority remove <game>")
            return
        name = " ".join(ctx.args[1:])
        if name not in pri:
            ctx.cli.print(f"not in list: {name}")
            return
        pri.remove(name)
        s.priority = pri
        s.save()
        ctx.cli.print(f"removed: {name}")
        return
    if sub == "move":
        if len(ctx.args) < 3:
            ctx.cli.print("usage: priority move <game> <delta>")
            return
        name = ctx.args[1]
        try:
            delta = int(ctx.args[2])
        except ValueError:
            ctx.cli.print("delta must be integer")
            return
        if name not in pri:
            ctx.cli.print(f"not in list: {name}")
            return
        idx = pri.index(name)
        new_idx = max(0, min(len(pri) - 1, idx + delta))
        pri.insert(new_idx, pri.pop(idx))
        s.priority = pri
        s.save()
        ctx.cli.print(f"moved {name}: {idx} -> {new_idx}")
        return
    if sub == "clear":
        s.priority = []
        s.save()
        ctx.cli.print("priority list cleared")
        return
    ctx.cli.print(f"unknown subcommand: {sub}")


async def _cmd_exclude(ctx: CommandContext) -> None:
    if not ctx.args:
        ctx.args = ["list"]
    sub = ctx.args[0].lower()
    s = _settings(ctx)
    excl: set[str] = set(s.exclude)
    if sub == "list":
        if not excl:
            ctx.cli.print("exclude list is empty")
            return
        for name in sorted(excl):
            ctx.cli.print(f"  {name}")
        return
    if sub == "add":
        if len(ctx.args) < 2:
            ctx.cli.print("usage: exclude add <game>")
            return
        name = " ".join(ctx.args[1:])
        excl.add(name)
        s.exclude = excl
        s.save()
        ctx.cli.print(f"excluded: {name}")
        return
    if sub == "remove":
        if len(ctx.args) < 2:
            ctx.cli.print("usage: exclude remove <game>")
            return
        name = " ".join(ctx.args[1:])
        excl.discard(name)
        s.exclude = excl
        s.save()
        ctx.cli.print(f"un-excluded: {name}")
        return
    if sub == "clear":
        s.exclude = set()
        s.save()
        ctx.cli.print("exclude list cleared")
        return
    ctx.cli.print(f"unknown subcommand: {sub}")


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
        ctx.cli.print(f"unknown mode: {name}")
        ctx.cli.print(f"valid: {', '.join(_MODE_NAMES)}")
        return
    s.priority_mode = _MODE_NAMES[name]
    s.save()
    ctx.cli.print(f"mode set to {name}")


async def _cmd_proxy(ctx: CommandContext) -> None:
    s = _settings(ctx)
    if not ctx.args:
        ctx.cli.print(f"proxy: {s.proxy or '—'}")
        return
    val = ctx.args[0]
    if val.lower() == "clear":
        s.proxy = URL()
        s.save()
        ctx.cli.print("proxy cleared")
        return
    s.proxy = URL(val)
    s.save()
    ctx.cli.print(f"proxy set to {s.proxy}")


async def _cmd_lang(ctx: CommandContext) -> None:
    s = _settings(ctx)
    if not ctx.args:
        ctx.cli.print(f"lang: {s.language}")
        return
    s.language = ctx.args[0]
    s.save()
    ctx.cli.print(f"lang set to {s.language} (effective on next start)")


async def _cmd_quality(ctx: CommandContext) -> None:
    s = _settings(ctx)
    if not ctx.args:
        ctx.cli.print(f"quality: {s.connection_quality}")
        return
    try:
        q = int(ctx.args[0])
    except ValueError:
        ctx.cli.print("quality must be an integer 0..2")
        return
    if not 0 <= q <= 2:
        ctx.cli.print("quality must be 0..2")
        return
    s.connection_quality = q
    s.save()
    ctx.cli.print(f"quality set to {q}")


_GETTABLE_KEYS = (
    "priority", "exclude", "priority_mode", "language", "proxy",
    "connection_quality", "tray_notifications", "enable_badges_emotes",
    "available_drops_check", "dark_mode", "autostart_tray",
)


async def _cmd_get(ctx: CommandContext) -> None:
    if not ctx.args:
        ctx.cli.print("known keys:")
        for k in _GETTABLE_KEYS:
            ctx.cli.print(f"  {k}")
        return
    key = ctx.args[0]
    s = _settings(ctx)
    if key not in s._settings:
        ctx.cli.print(f"unknown key: {key}")
        return
    val = getattr(s, key)
    if isinstance(val, PriorityMode):
        val = val.name.lower()
    ctx.cli.print(f"{key} = {val}")


async def _cmd_set(ctx: CommandContext) -> None:
    if len(ctx.args) < 2:
        ctx.cli.print("usage: set <key> <value>")
        return
    key, raw = ctx.args[0], " ".join(ctx.args[1:])
    s = _settings(ctx)
    if key not in s._settings:
        ctx.cli.print(f"unknown key: {key}")
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
                ctx.cli.print(f"valid modes: {', '.join(_MODE_NAMES)}")
                return
            v = _MODE_NAMES[raw]
        else:
            v = raw
    except Exception as exc:
        ctx.cli.print(f"can't parse value: {exc}")
        return
    setattr(s, key, v)
    s.save()
    ctx.cli.print(f"{key} = {getattr(s, key)}")


async def _cmd_save(ctx: CommandContext) -> None:
    ctx.twitch.save(force=True)
    ctx.cli.print("saved")


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
        ctx.cli.print(f"level: {logging.getLevelName(log.getEffectiveLevel())}")
        return
    name = ctx.args[0].upper()
    if name not in _LEVEL_BY_NAME:
        ctx.cli.print(f"valid: {', '.join(_LEVEL_BY_NAME)}")
        return
    log.setLevel(_LEVEL_BY_NAME[name])
    ctx.cli.print(f"level set to {name}")


async def _cmd_dump(ctx: CommandContext) -> None:
    s = _settings(ctx)
    cur = getattr(s._args, "dump", False)
    new = not cur if not ctx.args else ctx.args[0].lower() in ("1", "true", "on", "yes")
    s._args.dump = new
    ctx.cli.print(f"dump {'enabled' if new else 'disabled'}")
