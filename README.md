# TwitchDropsMiner CLI

> 📖 [中文说明](README_zh.md) · 🚀 **[入门指南 / Getting started](docs/getting-started.md)**

A headless, pure-CLI fork of [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner).
No tkinter, no tray — runs wherever Python runs, controlled from an interactive
shell.

<img width="1193" height="488" alt="TwitchDropsMiner CLI" src="https://github.com/user-attachments/assets/92cbb793-d4b4-4d66-843c-d589a6725260" />

## What it is

The upstream app mines timed Twitch drops by imitating "still watching" heartbeats
at the GraphQL layer — **no video or audio is downloaded at all**. It works well,
but its GUI makes it awkward on a VPS, in Docker, over SSH, or on a Pi.

This fork keeps the entire mining engine untouched and replaces the interface
layer with a CLI manager (`cli.py`) and a command shell (`commands.py`).
`gui.py` is still there: set `TDM_GUI=1` to go back to the upstream UI.

- **Headless first** — servers, containers, WSL, Raspberry Pi
- **Scriptable** — `--no-shell` for a service or cron
- **Observable** — one clean log line per state change; `log` to read them back
- **Upstream-friendly** — engine code is unmodified

## Features

From upstream: zero-bandwidth mining, game priority and exclusion lists, sharded
websockets (~199 channels), automatic campaign discovery, auto channel switching,
persistent login, auto-claiming, auto start/stop.

Added here: an interactive shell with live settings, `pause` / `resume` /
`reload`, manual channel selection, pipe-friendly output, and a **browser login
helper** that restores the full campaign catalogue plus automatic session renewal.

## Install

**Prebuilt** — from [Releases](https://github.com/LCBRST/TwitchDropsMiner-CLI/releases).
There are two builds, `TwitchDropsMiner-CLI_Linux` and
`TwitchDropsMiner-CLI_Windows.exe`; macOS has no prebuilt, use the source install.

```bash
chmod +x ./TwitchDropsMiner-CLI_Linux && ./TwitchDropsMiner-CLI_Linux   # Linux
```
```powershell
.\TwitchDropsMiner-CLI_Windows.exe                                     # Windows
```

**From source** — Python 3.10+, any of Linux / macOS / Windows:

```bash
git clone https://github.com/LCBRST/TwitchDropsMiner-CLI.git
cd TwitchDropsMiner-CLI
python3 -m venv venv
venv/bin/pip install -U pip wheel          # Windows: venv\Scripts\pip
venv/bin/pip install -r requirements.txt
python main.py
```

## Run

```bash
python main.py              # interactive shell
python main.py --no-shell   # no prompt, logs only
```

With no saved session it walks you through a one-time device code login and
stores the token in `cookies.jar`. Then:

```
priority add <game>     # what you want to mine
resume                  # start
```

### If no campaigns show up

Twitch only lets some login types see the campaign catalogue, and the ones this
program can mint for itself no longer qualify. A small **login helper**, run once
on a machine with Chrome, hands over a session that can — and the miner renews it
by itself from then on.

```
helper on     # then run tdm-login-helper on the desktop, against the address shown
helper        # shows the imported session and renewal state
helper renew  # force a renewal now instead of waiting for the deadline
```

Full walkthrough: **[docs/getting-started.md](docs/getting-started.md)**.
Automatic renewal needs a Chromium-based browser on the miner's machine — no
display required.

## Commands

`help` lists everything, `help <cmd>` explains one.

| | |
|---|---|
| `status` `version` `log [N]` `clear` `exit` | general |
| `whoami` `login` `helper [on\|off\|renew]` | login |
| `pause` `resume` `reload` `watch <login>` `unwatch` `claim` | mining |
| `inventory`(`inv`) `campaigns` `drops` | what is being mined |
| `channels [--all]` `online` | channels |
| `priority …` `exclude …` `mode …` `proxy …` `lang …` `quality …` `get`/`set` `save` | settings |
| `level <LEVEL>` `dump [on\|off]` | debug |

## CLI arguments

| Argument | |
|---|---|
| `-v` … `-vvvv` | raise log verbosity |
| `--no-shell` | no prompt (service mode) |
| `--no-watchdog` | disable the crash-restart supervisor |
| `--token <file>` | seed `cookies.jar` from a token file |
| `--dump` | dump every GQL response |
| `--debug-ws` / `--debug-gql` | debug websocket / GQL traffic |

A watchdog supervises the worker by default and restarts it on a crash (including
OOM or `kill -9`); each restart is logged to `log/restart.log`. A clean exit does
not restart.

## Files

| | |
|---|---|
| `settings.json` | all settings |
| `cookies.jar` | the saved login — **treat it as a password** |
| `imported-session.json` | session from the login helper — **also a credential** |
| `log/` | timestamped logs and command history |
| `lock.file` | single-instance lock |

## Common issues

- **Cannot connect to Twitch** — the default timeouts are tight; `quality 2`.
- **Behind a proxy** — `export https_proxy=…` or the `proxy` command.
- **Don't watch streams with the same account while mining** — progress is
  per-account and the two interfere.

More in the [guide](docs/getting-started.md#troubleshooting).

## Credits

- **[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)** —
  the original app and the entire mining engine this fork runs.
- **[rangermix/TwitchDropsMiner](https://github.com/rangermix/TwitchDropsMiner)** —
  the browser login helper and the integrity renewal design; this project
  implements the miner side of that protocol.

## License

MIT — © [DevilXD](https://github.com/DevilXD). See `LICENSE`.

## Contributing

PRs welcome. Register new commands in `commands.py`'s `_register_builtins()` and
document them in the [guide](docs/getting-started.md#commands).
