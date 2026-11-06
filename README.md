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

This fork keeps the mining engine and replaces the interface layer with a CLI.
The source is grouped by function: `twitchdropsminer/core/` (engine),
`common/` (settings, translations, utilities), `auth/` (browser sign-in and
session renewal), `web/` (management API and image cache), and `cli/` (shell and
commands). `main.py` is the entry point; build and install scripts live in
`tools/`.

```
twitchdropsminer/
  common/   constants, settings, translations, utils, exceptions, version
  core/     twitch engine, channel, inventory, websocket
  auth/     browser login, session import/renewal, sign-in server
  web/      management API, image cache
  cli/      CLIManager and command registry
main.py     entry point
tools/      build, install, cleanup, web-ui sync
```

- **Headless first** — servers, containers, WSL, Raspberry Pi
- **Scriptable** — `--no-shell` for a service or cron
- **Observable** — one clean log line per state change; `log` to read them back
- **Upstream-friendly** — engine code is unmodified

## Features

From upstream: zero-bandwidth mining, game priority and exclusion lists, sharded
websockets (~199 channels), automatic campaign discovery, auto channel switching,
persistent login, auto-claiming, auto start/stop.

Added here: an interactive shell with live settings, `pause` / `resume` /
`reload`, manual channel selection, pipe-friendly output, and a **browser
sign-in** the miner starts itself, which restores the full campaign catalogue
plus automatic session renewal.

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

**Linux, one command** — installs the browser and `Xvfb`, builds from source, and
cleans the build environment up afterwards:

```bash
wget -O install_linux.sh https://raw.githubusercontent.com/LCBRST/TwitchDropsMiner-CLI/main/tools/install_linux.sh
chmod +x install_linux.sh && ./install_linux.sh
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

With no saved session the miner opens a browser of its own and waits for you to
sign in — the window appears on that machine if it has a screen, and a URL to
open from anywhere if it does not. Then:

```
priority add <game>     # what you want to mine
resume                  # start
```

### If no campaigns show up

Twitch only lets some login types see the campaign catalogue, and the ones this
program can mint for itself no longer qualify. **`login browser`** starts a real
browser on the miner's own machine and keeps the session it captures — one that
can see everything, and that the miner renews by itself from then on.

```
login browser  # sign in through a browser the miner starts itself
login status   # shows the imported session and renewal state
login renew    # force a renewal now instead of waiting for the deadline
```

Full walkthrough: **[docs/getting-started.md](docs/getting-started.md)**.
Signing in and automatic renewal both need a Chromium-based browser on the
miner's machine. A machine with no screen also needs `Xvfb`, for that browser to
draw on.

## Commands

`help` lists everything, `help <cmd>` explains one.

| | |
|---|---|
| `status` `version` `log [N]` `copy [N]` `clear` `exit` | general |
| `whoami` `login [browser\|status\|cancel\|renew\|device\|doctor]` | login |
| `pause` `resume` `reload` `watch <login>` `unwatch` `claim` | mining |
| `inventory`(`inv`) `campaigns` `drops` | what is being mined |
| `channels [--all]` `online` | channels |
| `priority …` `exclude …` `mode …` `proxy …` `lang …` `quality …` `get`/`set` `save` | settings |
| `level <LEVEL>` `dump [on\|off]` | debug |
| `api [status\|on\|off\|auth\|open\|copy\|file\|token\|rotate]` | management API and web dashboard |

## Web dashboard

The miner can serve a small management page at the same time as it mines. It is
off by default; once enabled it listens on all interfaces, so a phone or another
computer on the same network can open it:

```
api on        # starts :8091 and generates a token; prints the LAN address
api open      # opens the dashboard already signed in on this machine
api status    # shows the LAN address to use from another device
```

If the browser does not open by itself, `api copy` puts the token on the
clipboard and `api token` prints it. While authentication is on (the default),
every `/api` request needs that token.

Over SSH, `api copy` and `copy [N]` use the terminal's OSC 52 clipboard, so no
clipboard utility is needed on the remote machine. If the terminal blocks OSC 52,
`copy [N]` also writes `copy.txt`, and `api file` writes the token to
`api-token.txt` (mode 600) next to the executable — fetch it with scp/SFTP and
delete it afterwards.

The page shows live drop/campaign progress, channels, settings and logs, and
can pause/resume mining, pick a channel, claim drops and change settings. It can
also start or cancel a Twitch browser sign-in, renew the imported session, and
drive the sign-in browser inside the page — the viewer is proxied through the
dashboard's own port, so only that port needs forwarding. `api token
<your-token>` sets a custom management token; `api rotate` generates a random
one. Token authentication is optional: `api auth off` (or
`set api_auth_enabled false`) makes the dashboard connect without asking. That
leaves the miner controllable by anything that can reach its port, so only do
it on a trusted network.

Reward and campaign artwork is cached under `cache/images/` and served through
the dashboard, so the page does not need the Twitch CDN. Images belonging to
campaigns that have left the inventory are deleted automatically; this is
checked on every inventory refresh and every 30 minutes.

The front-end is a separate project,
[TwitchDropMiner_WebAddon](https://github.com/LCBRST/TwitchDropMiner_WebAddon);
the HTTP contract is documented in its `API.md`.

The API can control the miner. It is protected by the token, but on an untrusted
network set `api_host` back to `127.0.0.1` to keep it on this machine.

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
| `imported-session.json` | the session captured from the sign-in browser — **also a credential** |
| `log/` | timestamped logs and command history |
| `lock.file` | single-instance lock |
| `cache/images/` | dashboard artwork downloaded from Twitch; safe to delete |

## Common issues

- **Cannot connect to Twitch** — the default timeouts are tight; `quality 2`.
- **Behind a proxy** — `proxy <url>`; HTTP requests and the sign-in/renewal
  browser both use it (the browser does not support proxy authentication).
- **Don't watch streams with the same account while mining** — progress is
  per-account and the two interfere.

More in the [guide](docs/getting-started.md#troubleshooting).

## Credits

- **[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)** —
  the original app and the entire mining engine this fork runs.
- **[rangermix/TwitchDropsMiner](https://github.com/rangermix/TwitchDropsMiner)** —
  the integrity renewal design: replaying a captured session into a headless
  browser and letting Kasada's own script mint the next proof.

## License

MIT — © [DevilXD](https://github.com/DevilXD). See `LICENSE`.

## Contributing

PRs welcome. Register new commands in `twitchdropsminer/cli/commands.py`'s
`_register_builtins()` and
document them in the [guide](docs/getting-started.md#commands).
