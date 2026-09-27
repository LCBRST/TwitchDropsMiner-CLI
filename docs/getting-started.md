# Getting started

Everything needed to go from nothing to mining drops, on a machine with no
desktop.

- [What this is](#what-this-is)
- [Requirements](#requirements)
- [Install](#install)
- [First run](#first-run)
- [Getting the full campaign list](#getting-the-full-campaign-list)
- [Keeping the login alive](#keeping-the-login-alive)
- [Everyday use](#everyday-use)
- [Commands](#commands)
- [Files](#files)
- [Running it as a service](#running-it-as-a-service)
- [Troubleshooting](#troubleshooting)
- [How it fits together](#how-it-fits-together)
- [Credits](#credits)

---

## What this is

A pure command-line build of TwitchDropsMiner. It mines timed Twitch drops by
imitating the "still watching" heartbeats at the GraphQL layer, so **no video or
audio is ever downloaded**. The original desktop app needs a GUI and a system
tray; this build replaces that layer with an interactive shell so it can run on a
VPS, in a container, over SSH, or on a Raspberry Pi.

The mining engine is the upstream one and is not modified.

## Requirements

| | |
|---|---|
| Python | 3.10 or newer (source install) |
| OS | Linux, macOS, Windows — no display needed |
| Network | outbound HTTPS to `twitch.tv`, `gql.twitch.tv`, `spade.twitch.tv` |
| Browser | *only* for automatic login renewal — see [below](#keeping-the-login-alive) |

About 65 MB of RAM once it is mining, and no bandwidth beyond API traffic.

## Install

### Prebuilt binary

From [Releases](https://github.com/LCBRST/TwitchDropsMiner-CLI/releases) there
are two builds, `TwitchDropsMiner-CLI_Linux` and `TwitchDropsMiner-CLI_Windows.exe`.
There is no prebuilt macOS binary — on a Mac, use the source install below.

```bash
chmod +x ./TwitchDropsMiner-CLI_Linux && ./TwitchDropsMiner-CLI_Linux    # Linux
```
```powershell
.\TwitchDropsMiner-CLI_Windows.exe                                     # Windows
```

### From source

```bash
git clone https://github.com/LCBRST/TwitchDropsMiner-CLI.git
cd TwitchDropsMiner-CLI
python3 -m venv venv
venv/bin/pip install -U pip wheel          # Windows: venv\Scripts\pip
venv/bin/pip install -r requirements.txt
python main.py
```

`requirements.txt` also lists the GUI dependencies (`Pillow`, `pystray`). They are
only needed to build the upstream desktop app and are unused here — install just
`aiohttp yarl prompt_toolkit truststore` if you want to keep it lean.

## First run

```bash
python main.py              # interactive shell
python main.py --no-shell   # no prompt, logs only (for a service)
```

With no saved session the program starts a **device code login**: it prints a URL
and a short code, you enter the code in a browser once, and the token is saved to
`cookies.jar`. Nothing else is needed to start mining.

Then tell it what to mine:

```
priority add <game>     # add games you care about
mode priority_only      # mine only those (the default)
resume                  # start mining
```

`help` lists every command; `help <command>` explains one.

## Getting the full campaign list

**Read this if `campaigns` shows only a handful of entries, or the log says
`campaign discovery is not working`.**

Twitch decides which campaigns an account can *see* based on which client the
login token was issued to, and it has closed that door for every client this
program can log into on its own. Such a session can still mine whatever is
already in progress, but it cannot discover new campaigns.

The way around it is the **login helper**: a small program you run on a computer
that has Google Chrome. It opens Chrome, lets you sign in normally, and hands the
resulting browser session — which *can* see the full catalogue — to the miner.

You only do this when the miner asks for it or when campaigns are missing.

### 1. Open the endpoint

In the miner's shell:

```
helper on
```

It prints something like:

```
login helper: enabled
listening on 0.0.0.0:8090
from another machine: http://192.0.2.10:8090
the helper runs on this machine: http://127.0.0.1:8090
run it where Chrome is installed: tdm-login-helper --tdm http://192.0.2.10:8090
```

`0.0.0.0` is a *listening* address — nothing can connect to it. From another
machine, use the address on the `from another machine` line. If the miner has
more than one — a VPN, a container bridge — they are all listed, and one of them
is a line reminding you to pick whichever the helper can reach.

**The addresses above are an example.** Use the ones your own miner prints;
`192.0.2.x` is a reserved documentation range that will never be your machine.

Allow the port through your firewall if you are connecting from elsewhere.

### 2. Run the helper

Download the login helper from
[rangermix/TwitchDropsMiner releases](https://github.com/rangermix/TwitchDropsMiner/releases)
— pick the archive matching the **desktop's** OS and CPU, not the miner's.

```bash
tdm-login-helper --tdm <miner-address>
```

Sign into Twitch in the Chrome window it opens, including any 2FA. Wait for it to
report success; it then closes Chrome and deletes its temporary profile. Your
normal Chrome profile is not touched.

### 3. Check

```
helper
```

should now show `imported session: active, expires ...`, and the miner's campaign
count should jump to the full catalogue. It takes effect immediately — no restart.

The endpoint then **closes itself** and prints a line saying so. It accepts
credentials from anyone who can reach it, and nothing needs it once the session
is in — renewal works from the stored session. That means a *later* helper run
needs `helper on` again first; a session imported once lasts until renewal cannot
keep up with it.

## Keeping the login alive

The imported session carries an integrity proof that expires after about 16
hours. The miner renews it automatically, a few minutes before it lapses: it
starts a temporary **headless** Chromium, replays the captured session into it,
and lets the page mint a fresh proof, which is verified before being adopted.

**This needs a Chromium-based browser on the machine running the miner.** Nothing
else about the machine changes — no display, no desktop.

- It finds `chromium` / `chrome` on `PATH`, then the usual install locations
  (including Edge on Windows).
- To point it somewhere specific:

  ```
  set renewal_browser_path C:\Program Files\Google\Chrome\Application\chrome.exe
  set renewal_browser_path /usr/bin/google-chrome      # Linux and macOS
  ```

- `helper` reports the state: `renewal: automatic, using ...`, or
  `renewal: unavailable - <why>`.

You can trigger a renewal on demand instead of waiting for the deadline:

```
helper renew
```

If renewal keeps failing the miner does not break: it retries with a backoff,
keeps using the current session, and falls back to `cookies.jar` once the session
really expires. Run the helper again to get a fresh one.

### Installing a browser on Linux

> **Do not use `apt install chromium` on Ubuntu 20.04 or newer.** That installs a
> *snap* wrapper, which generally cannot be used for this. Flatpak has the same
> problem.

| Distribution | |
|---|---|
| Debian / Ubuntu | Google Chrome's `.deb`:<br>`wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb`<br>`sudo apt install ./google-chrome-stable_current_amd64.deb`<br>On ARM use `..._current_arm64.deb` |
| Fedora / RHEL | `sudo dnf install https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm` |
| Debian (proper) | `sudo apt install chromium` — a real package here, unlike on Ubuntu |
| Arch | `sudo pacman -S chromium` |
| Alpine, containers | `apk add chromium` |
| No root at all | `pip install playwright && playwright install chromium` — puts a Chromium in your home directory, no system packages needed |

Then check it: `google-chrome --version` (or `chromium --version`) should print a
version, and `helper` should change to `renewal: automatic, using …`.

Running as root — inside a container, for instance — is handled for you: the
browser is started with `--no-sandbox`, which Chromium requires in that case.

## Everyday use

| | |
|---|---|
| See what is happening | `status`, `drops`, `inventory` |
| Change what gets mined | `priority ...`, `exclude ...` |
| Pause without quitting | `pause` / `resume` |
| Pick a channel by hand | `watch <channel>` / `unwatch` |
| Force a refresh | `reload` |
| Check the login | `whoami`, `helper` |

## Commands

`help` lists everything; this is the full set.

**General** — `help [cmd]`, `status`, `version`, `log [N]`, `clear`,
`exit` / `quit` / `q`

**Login** — `whoami`, `login`, `helper [on|off|renew]`

**Mining** — `pause`, `resume`, `reload`, `watch <login>`, `unwatch`, `claim`

**Inventory** — `inventory` (`inv`), `campaigns`, `drops`

**Channels** — `channels [--all]`, `online`

**Settings** — everything below persists to `settings.json`:

| Command | |
|---|---|
| `priority list \| add <game> \| remove <game> \| move <game> <delta> \| clear` | games to mine first |
| `exclude list \| add <game> \| remove <game> \| clear` | games to never mine |
| `mode [priority_only \| ending_soonest \| low_avbl_first]` | what to mine when nothing on the priority list is available |
| `proxy [<url> \| clear]` | HTTP proxy |
| `lang [code]` | interface language |
| `quality [0..2]` | connection timeout multiplier — raise it on a slow link |
| `get [key]` / `set <key> <value>` | read and write any setting |
| `save` | write settings now |

**Debug** — `level <LEVEL>`, `dump [on|off]`

## Files

Everything lives next to the executable (or the repository root).

| File | |
|---|---|
| `settings.json` | all settings |
| `cookies.jar` | the saved login — **treat it as a password** |
| `imported-session.json` | the session delivered by the login helper — **also a credential** |
| `lock.file` | single-instance lock; safe to delete after a crash |
| `log/` | timestamped logs plus command history |

Back up `cookies.jar` and `imported-session.json` if you want to move the
installation; both are credentials, so keep them private and never commit them.

## Running it as a service

`--no-shell` keeps it running without an interactive prompt, which is what you want
under a supervisor. The built-in watchdog already restarts the worker on a crash,
so add `--no-watchdog` when something else is supervising it too.

**Linux (systemd):**

```ini
[Unit]
Description=TwitchDropsMiner CLI
After=network-online.target

[Service]
WorkingDirectory=/opt/tdm
ExecStart=/opt/tdm/venv/bin/python /opt/tdm/main.py --no-shell --no-watchdog
Restart=always
User=tdm

[Install]
WantedBy=multi-user.target
```

**Windows (Task Scheduler):** run this from an elevated prompt, adjusting the
paths — use `pythonw.exe` so no console window appears:

```powershell
schtasks /create /tn TwitchDropsMiner /sc onstart /ru %USERNAME% ^
  /tr "C:\tdm\venv\Scripts\pythonw.exe C:\tdm\main.py --no-shell --no-watchdog"
```

Paths containing spaces need extra quoting; [NSSM](https://nssm.cc/) is easier if
you want a real service that restarts on failure.

**macOS (launchd):** a LaunchAgent with `RunAtLoad` and `KeepAlive`, running the
same command.

Closing the console window stops it on every platform, so run it under the
supervisor rather than by hand.

## Troubleshooting

**No campaigns, or only a few.** The login cannot see the catalogue — see
[Getting the full campaign list](#getting-the-full-campaign-list).

**`Cannot connect to Twitch`.** The default timeouts are tight. Raise them:

```
quality 2
```

Behind a proxy, either set `https_proxy` in the environment or use
`proxy http://127.0.0.1:7890`. A transparent proxy on a router usually needs
nothing beyond a higher `quality`.

**The helper reports `SESSION_HELPER_NETWORK`.** It cannot reach the miner. Check
that `helper` shows `enabled`, that the port is listening
(`ss -ltnp | grep 8090` on Linux, `netstat -ano | findstr 8090` on Windows), that
you used `127.0.0.1` rather than `0.0.0.0`, and that the firewall allows it.

**The helper reports `SESSION_HELPER_REJECTED`.** The miner refused the session;
the log line `Rejected an imported session: <code>` says why:

| Code | |
|---|---|
| `FORMAT` / `IDENTITY` / `AUTH` | the captured session did not validate |
| `ACCOUNT_MISMATCH` | the helper signed into a different account than the miner is using |
| `CATALOG` | that session cannot read the campaign list |

**Renewal is unavailable.** Check the reason in `helper` output. The usual one is
that no Chromium-based browser was found — see
[Keeping the login alive](#keeping-the-login-alive).

**Renewal failed with `BROWSER_START`.** The browser was found but would not
start: usually missing shared libraries on a minimal server, or a snap/flatpak
wrapper.

**Do not watch streams with the same account while mining.** Twitch counts drop
progress per account, and watching at the same time confuses the reporting.

## How it fits together

Only useful if you intend to change something.

```
              +---------------------+        +-----------------------+
              |  twitch.py engine   |  uses  |   gui interface       |
              | (state machine,     +------->|   (tray, status,      |
              |  GQL, websockets)   |        |    channels, inv,     |
              +----------+----------+        |    progress, login)   |
                         |                   +----------+------------+
                         | self.gui = ...               |
                         |                              |
              +----------v----------+        +----------v-----------+
              |  cli.CLIManager     |        |  gui.GUIManager      |
              |  (default)          |  XOR   |  (TDM_GUI=1)         |
              |                     |        |                      |
              | + interactive shell |        |  + tk/pystray UI     |
              +----------+----------+        +----------------------+
                         |
              +----------v----------+
              |  commands.py        |
              |  CommandRegistry    |
              +---------------------+
```

The engine never imports `cli` or `commands`; it only ever calls `self.gui.*`.
`CLIManager` implements every method the engine uses — `tray.change_icon`,
`status.update`, `channels.set_watching/clear/display`, `progress.display`,
`inv.add_campaign`, `websockets.update`, `login.ask_login`,
`login.ask_enter_code`, `set_games`, `display_drop`, `clear_drop`, `print`,
`save`, `start`, `stop`, `close`, `close_window`, `prevent_close`,
`grab_attention`, `coro_unless_closed`, `wait_until_closed`, `running`,
`close_requested`.

New commands are registered in `commands.py`'s `_register_builtins()`.

## Credits

This project is a command-line fork and would not exist without the work of
others:

- **[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)** —
  the original application, and the whole mining engine this fork runs: the GQL
  pipeline, websocket sharding, drop tracking and channel switching are all
  upstream work. Licensed MIT.
- **[rangermix/TwitchDropsMiner](https://github.com/rangermix/TwitchDropsMiner)** —
  the browser login helper and the integrity renewal design. The helper protocol,
  the Kasada issuance approach and the keep-it-renewable idea all come from that
  fork; this project implements the miner side of it.
- Twitch's drops system, and every contributor to the upstream project.

## License

MIT, the same as upstream. Original copyright belongs to
[DevilXD](https://github.com/DevilXD); see `LICENSE`.
