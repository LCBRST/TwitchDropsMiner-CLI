# Getting started

Everything needed to go from nothing to mining drops, on a machine with no
desktop — signing in is the one step that wants a screen, and `Xvfb` stands in
for one where there is none.

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
| OS | Linux, macOS, Windows — no display needed, but signing in starts a browser, so a machine with no screen also needs `Xvfb` |
| Network | outbound HTTPS to `twitch.tv`, `gql.twitch.tv`, `spade.twitch.tv` |
| Browser | a Chromium-based one, for signing in and for automatic login renewal — see [below](#getting-the-full-campaign-list) |

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

### Linux, one command

Fetches this script, runs it, done:

```bash
wget -O install_linux.sh https://raw.githubusercontent.com/LCBRST/TwitchDropsMiner-CLI/main/install_linux.sh
chmod +x install_linux.sh
./install_linux.sh
```

It installs what this program needs from the system (a Chromium-based browser, and
`Xvfb` for a machine with no screen), downloads the source, builds a self-contained
binary next to where you ran it, and then removes the source and the build
environment again. What is left is the browser, `Xvfb`, and the binary.

```
./install_linux.sh --dry-run     # say what it would do, change nothing
./install_linux.sh --dir ~/tdm   # install somewhere else
./install_linux.sh --keep-source # leave the source and venv behind
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

With no saved session the program **opens a browser and waits for you to sign
in**. That session is the only login that can see the whole catalogue, so it is
the one worth doing - see
[Getting the full campaign list](#getting-the-full-campaign-list) for where the
window appears, and what to do on a machine with no screen.

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

The way around it is to **sign in through a browser the miner starts itself**.
It is a real browser, on the miner's own machine and address, so the session it
ends up holding is one the miner can go on using. Nothing is handed over, and
there is no second program to install.

You are offered this on a first run, and whenever the campaign list comes back
short. To ask for it yourself:

```
login browser
```

### If the miner has a screen

A browser window opens **on the miner**, and that is the whole story:

```
a browser window has opened on this machine - sign in to Twitch there
```

Sign in there, including any 2FA or email code. The window closes itself once the
session is in.

### If it does not

The miner prints addresses instead, one per way it can be reached:

```
sign in at http://192.0.2.10:8090/login/xxxxxxxx
on this machine: http://127.0.0.1:8090/login/xxxxxxxx
```

Open one from anywhere — a laptop, a phone. What you get is not a copy of Twitch
in *your* browser: it is a live view of the browser running **on the miner**, with
your mouse and keyboard going back into it. Click into the picture and use it as
if you were sitting there. Pasting works too, which is how a password manager
gets a password in.

On a headless Linux machine the miner starts `Xvfb` to be the screen the browser
draws on. If `Xvfb` is missing it says so, rather than handing you an address
that leads nowhere:

```
sudo apt install xvfb      # Debian/Ubuntu - use your distribution's package
```

**The `192.0.2.x` addresses above are examples.** Use the ones your own miner
prints; `192.0.2.0/24` is a reserved documentation range that will never be your
machine.

Allow the port through your firewall if you are signing in from elsewhere.

### Check

```
login status
```

should now show `imported session: active`, and the campaign count should jump to
the full catalogue. It takes effect immediately — no restart.

The page then **closes itself**. It is a way in, not a control panel, and nothing
needs it once the session is in — renewal works from the stored session. A later
sign-in needs `login browser` again.

### Why it might not work

Twitch is the only thing that can refuse this, and the one lever it gives you is
consistency: it is fussier about a sign-in whose machine, clock and timezone do
not match where the account normally signs in from. If the sign-in is rejected,
set the machine's timezone correctly before anything else.

`login device` logs in the old way, without a browser, for a machine that has
none. It authenticates as a client that **cannot see the campaign list**, so it
is a way to keep mining what is already in progress, not a way to discover
anything.

## Keeping the login alive

The imported session carries an integrity proof with a lifetime Twitch decides,
and it is not generous: it measured sixteen hours for an anonymous request and
one hour for a signed-in one. The miner renews it automatically, a few minutes
before it lapses: it
starts a temporary **headless** Chromium, replays the captured session into it,
and lets the page mint a fresh proof, which is verified before being adopted.

**This needs a Chromium-based browser on the machine running the miner** — the
same one signing in uses. Nothing else about the machine changes — no display, no
desktop. (A machine that has no browser at all can still run on `login device`,
which sees fewer campaigns.)

- It finds `chromium` / `chrome` on `PATH`, then the usual install locations
  (including Edge on Windows).
- To point it somewhere specific:

  ```
  set renewal_browser_path C:\Program Files\Google\Chrome\Application\chrome.exe
  set renewal_browser_path /usr/bin/google-chrome      # Linux and macOS
  ```

- `login status` reports the state: `renewal: automatic, using ...`, or
  `renewal: unavailable - <why>`.

You can trigger a renewal on demand instead of waiting for the deadline:

```
login renew
```

If renewal keeps failing the miner does not break: it retries with a backoff,
keeps using the current session, and falls back to `cookies.jar` once the session
really expires. `login browser` gets a fresh one.

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
version, and `login status` should change to `renewal: automatic, using …`.

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
| Check the login | `whoami`, `login status` |

## Commands

`help` lists everything; this is the full set.

**General** — `help [cmd]`, `status`, `version`, `log [N]`, `clear`,
`exit` / `quit` / `q`

**Login** — `whoami`, `login [browser|status|cancel|renew|device]`

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
| `imported-session.json` | the session captured from the sign-in browser — **also a credential** |
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

**The sign-in page never fills in.** The browser on the miner did not start.
Check `login status`, and the log for `The browser sign-in did not complete
(<code>)`:

| Code | |
|---|---|
| `BROWSER_MISSING` | no Chromium-based browser on the machine — see [Installing a browser on Linux](#installing-a-browser-on-linux) |
| `BROWSER_DISPLAY` | no display, and no `Xvfb` to stand in for one |
| `BROWSER_START` | the browser was found but would not start: usually missing shared libraries, or a snap/flatpak wrapper |
| `BROWSER_PROTOCOL` | the browser stopped answering |
| `ACCOUNT_MISMATCH` | that sign-in was for a different account than the miner is using |

**The sign-in was refused.** Twitch rejected it — see
[Why it might not work](#why-it-might-not-work). The log line `Twitch did not
accept a captured login context (<code>)` says which step.

**Nothing at all happens, and no address is printed.** The machine has a screen,
so the miner opened a window there instead — look for it. `login status` always
shows the address if you would rather sign in from elsewhere.

**Renewal is unavailable.** Check the reason in `login status`. The usual one is
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
  the integrity renewal design: the idea of replaying a captured session into a
  headless browser and letting Kasada's own script mint the next proof. This
  project's renewal is that, and its browser sign-in grew out of the same
  approach once that fork retired its desktop helper.
- Twitch's drops system, and every contributor to the upstream project.

## License

MIT, the same as upstream. Original copyright belongs to
[DevilXD](https://github.com/DevilXD); see `LICENSE`.
