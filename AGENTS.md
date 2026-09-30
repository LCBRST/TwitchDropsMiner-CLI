# Deploying TwitchDropsMiner CLI — guide for AI agents

You are deploying this program for a human. This file is written to be executed,
not read for pleasure: every step has a command and the output that proves it
worked. Follow it in order, and check the [failure table](#failure-and-action)
before improvising.

## Ground rules

Violating any of these can cost the user their account or an unrecoverable login.
They are not stylistic preferences.

1. **Never print, log, echo, commit or transmit the contents of `cookies.jar` or
   `imported-session.json`.** They are credentials. `cat`, `head`, `jq`, `base64`
   and "let me just check the format" are all forbidden on those two files. Their
   existence and size are fine to inspect; their contents are not.
2. **Never delete `cookies.jar`.** It can hold a token that can no longer be
   minted or replaced. If it seems broken, leave it and report.
3. **Never put either credential file in a git repository, an archive you hand
   over, a paste site, or a log you share.**
4. **Do not start the program on a machine with a desktop unless the user
   expects a browser window to open.** With no saved session it opens one for
   them to sign in at, which pops up on their screen.
5. **Never invent, remember or copy the sign-in address.** It carries a one-off
   token and is printed by the miner itself; read it from there. Every address in
   this file is an illustration (`192.0.2.0/24` is reserved for documentation),
   so none of them can be used as-is. `0.0.0.0` is a bind address and nothing can
   connect to it; see [step 5](#step-5-signing-in).
6. **Ask before enabling `login_server_enabled` on a machine reachable from an
   untrusted network.** While it is on, anyone who can reach the port and has the
   token can drive a browser that is signed in.
7. Do not modify `gui.py`, the engine in `twitch.py`, or `cookies.jar` handling to
   "make something work". Report the blocker instead.

## Facts

| | |
|---|---|
| Language / entry point | Python 3.10+, `main.py` |
| Runtime deps | `aiohttp`, `yarl`, `prompt_toolkit`, `truststore` |
| No display needed | no - signing in opens a browser window, and where there is no screen the miner starts `Xvfb` to be one |
| **Data directory** | **the folder containing `main.py` (source) or the executable (build)** — not the current working directory |
| Files it creates there | `settings.json`, `cookies.jar`, `imported-session.json`, `lock.file`, `log/` |
| Listeners it opens | none by default; one TCP port while a sign-in is open, and only where nobody can see the miner's screen |
| Release builds | Linux and Windows; **no macOS binary** |
| Upstream | DevilXD/TwitchDropsMiner (the mining engine) |
| Sign-in | a headful Chromium the miner starts itself; the user drives it directly, or through a page it serves |

The data-directory rule matters: the program resolves it from `sys.argv[0]`. If
you launch it from somewhere else, the settings and login still live next to the
program file. Wrapping the entry point in a Python snippet that sets
`sys.argv[0]` yourself (for example via `runpy.run_path`) **changes where it
writes**, which is an easy way to create a second, empty profile and make it look
like the login is gone.

## Step 1: install

Prebuilt, from this repository's releases page. Only two builds exist —
`TwitchDropsMiner-CLI_Linux` and `TwitchDropsMiner-CLI_Windows.exe`. **There is no
prebuilt macOS binary**; on a Mac use the source install.

```bash
chmod +x ./TwitchDropsMiner-CLI_Linux && ./TwitchDropsMiner-CLI_Linux   # Linux
```
```powershell
.\TwitchDropsMiner-CLI_Windows.exe                                     # Windows
```

Source (Linux, macOS or Windows):

```bash
git clone https://github.com/LCBRST/TwitchDropsMiner-CLI.git
cd TwitchDropsMiner-CLI
python3 -m venv venv
venv/bin/pip install -U pip wheel          # Windows: venv\Scripts\pip
venv/bin/pip install -r requirements.txt
```

`requirements.txt` also pulls `Pillow` and `pystray`, which are only needed to
build the upstream desktop app. `venv/bin/pip install aiohttp yarl prompt_toolkit
truststore` is a smaller, equivalent install for this build.

## Step 2: first run

Start it. Do this on a machine where a browser window is acceptable — with no
saved session, one opens:

```bash
python main.py               # interactive shell
python main.py --no-shell    # no prompt, logs only — use this for a service
```

With no saved session it opens a browser and waits for the user to sign in. On a
machine with a screen the window is right there; on one without, it prints an
address to open from elsewhere (see [step 5](#step-5-signing-in)).

**The user is the only one who can complete this** — there is no login an agent
can perform on their behalf. If they are not available, stop and say so.

Confirm it is running:

```
status          # engine state, watched channel, websocket state
whoami          # login status and Twitch user id
```

## Step 3: verify mining actually works

```
priority add <game>     # add at least one game
mode priority_only      # mine only priority-list games (default)
resume                  # start
drops                   # should show a campaign with a progress bar
```

The counters that matter:

- `campaigns` — number of campaigns the login can see.
- `drops` — the active drop and its progress.

**A working install keeps advancing the drop progress.** Nothing else proves it;
"no errors" does not.

## Step 4: decide whether the login can see the catalogue

Read the campaign count:

```
campaigns
```

| What you see | Meaning | Action |
|---|---|---|
| Around a hundred or more | the login can see the catalogue | skip to [step 6](#step-6-keep-the-login-alive) |
| A handful - single digits, and they are the ones already in progress | **the login cannot see the catalogue** | do [step 5](#step-5-signing-in) |
| Log contains `campaign discovery is not working` | same as above | do [step 5](#step-5-signing-in) |

This is the single most common deployment problem, and it is not a bug.

Twitch gates the campaign catalogue on the client the login token was issued to.
The clients this program can log into by itself no longer qualify. Such a session
still mines whatever is already in progress, so the failure looks like a healthy
miner with a suspiciously short list.

## Step 5: signing in

This is the fix for a login that cannot see the catalogue, and it is the one step
that needs the user. Everything else here an agent can do alone.

The browser runs **on the miner**, not on the machine the user is sitting at, so
the session it produces is one the miner can go on using. Nothing is handed over
between machines, and there is nothing to install anywhere.

```
login browser
```

### If the miner has a screen

The browser window opens on it and that is the whole story. The miner prints:

```
a browser window has opened on this machine - sign in to Twitch there
```

Tell the user to sign in there, including any 2FA or email code. The window closes
itself once the session is in.

### If it does not

The miner prints one address per way it can be reached:

```
sign in at http://192.0.2.10:8090/login/xxxxxxxx
on this machine: http://127.0.0.1:8090/login/xxxxxxxx
```

**Hand the user one of those addresses, exactly as printed** — the long random
part is a one-off token and is the only thing that makes the page work. What they
see is not Twitch rendered in their own browser: it is a live view of the miner's
browser, with their mouse and keyboard going back into it. They click into the
picture and use it as if they were sitting at the miner. Pasting works, which is
how a password manager gets a password in.

`0.0.0.0` is a bind address and connecting to it fails. When the host has several
addresses — a VPN, a container bridge — all of them are listed; do not assume the
first one is right, and do not skip that check on a multi-homed host. Make sure
the port is allowed through the firewall.

On a headless Linux host the miner starts `Xvfb` to be the screen the browser
draws on. If it is missing, the miner says so instead of printing an address that
leads nowhere:

```
sudo apt install xvfb      # Debian/Ubuntu; use the distribution's own package
```

### Confirm it

```
login status
```

Expected, and effective immediately with no restart:

```
browser sign-in: done
imported session: active
```

Then re-check `campaigns` — it should jump to the full catalogue. The page closes
itself shortly afterwards; that is normal and not a failure.

### If it does not work

Twitch is the only thing that can refuse this. It is fussier about a sign-in whose
machine, clock and timezone do not match where the account normally signs in
from — check the timezone first, and do not promise the user a duration.

`login device` logs in without a browser, for a machine that has none. It
authenticates as a client that **cannot see the catalogue**, so it keeps existing
mining going and discovers nothing. Do not reach for it as a workaround.

## Step 6: keep the login alive

The imported session carries an integrity proof whose lifetime Twitch decides,
and it can be short: sixteen hours was measured for an anonymous request, one
hour for a signed-in session. Do not promise a duration. The miner renews it
automatically a few minutes before it lapses, by starting a temporary headless
Chromium on the miner's own machine.

Requirements and checks:

| | |
|---|---|
| Required | a Chromium-based browser on the **miner's** machine |
| Auto-detected | `chromium` / `chrome` on `PATH`, then platform install locations (including Edge on Windows) |
| Override | `set renewal_browser_path /path/to/chrome` |
| Status | `login status` shows `renewal: automatic, using …` or `renewal: unavailable - <reason>` |
| **Installing one on Linux** | see the table below |
| On Ubuntu 20.04+ | **`apt install chromium` gives you a snap wrapper and will not work.** So does flatpak |

Install a browser on Linux with one of these. All of them have been checked to
exist; pick the one matching the host.

| Distribution | |
|---|---|
| Debian / Ubuntu | `wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb && sudo apt install ./google-chrome-stable_current_amd64.deb` (ARM: `..._current_arm64.deb`) |
| Fedora / RHEL | `sudo dnf install https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm` |
| Debian (proper) | `sudo apt install chromium` — a real package here, unlike on Ubuntu |
| Arch | `sudo pacman -S chromium` |
| Alpine, containers | `apk add chromium` |
| No root available | `pip install playwright && playwright install chromium` — installs a Chromium under the user's home directory |

Verify with `google-chrome --version` (or `chromium --version`), then re-run
`login status` and confirm it no longer says renewal is unavailable. Running as root is
handled: the browser is started with `--no-sandbox`, which Chromium requires in
that case.

Force one now instead of waiting for the deadline:

```
login renew
```

Then re-run `login status` after ~15 seconds and look for a `last renewed:` line. The
log will contain `Renewed the imported session, valid for another …`.

**Renewal failing is not fatal.** The miner retries with a backoff and keeps using
the current session until it genuinely expires, then falls back to `cookies.jar`.

## Step 7: running it as a service

Use `--no-shell`, and disable the built-in watchdog when an external supervisor
is present, so the two do not fight.

Linux, systemd:

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

Windows, Task Scheduler (elevated prompt; `pythonw.exe` avoids a console window,
and paths with spaces need further quoting):

```powershell
schtasks /create /tn TwitchDropsMiner /sc onstart /ru %USERNAME% ^
  /tr "C:\tdm\venv\Scripts\pythonw.exe C:\tdm\main.py --no-shell --no-watchdog"
```

macOS: a LaunchAgent with `RunAtLoad` and `KeepAlive` running the same command.

On every platform, SIGTERM (Linux/macOS) or terminating the process (Windows)
shuts it down cleanly — and closing the console window kills it, so it must run
under the supervisor rather than by hand.

## Verification checklist

A deployment is done when all of these hold:

- [ ] The process is running and `status` shows a state other than an error.
- [ ] `whoami` reports a user id.
- [ ] `campaigns` reports a realistic count, not single digits.
- [ ] `drops` shows a campaign and its progress **increases over a few minutes**.
- [ ] `login status` shows `imported session: active` (if step 5 was needed).
- [ ] `login status` shows `renewal: automatic` (if the session must outlive the
      current proof).
- [ ] `log/` contains no repeating error.

## Failure and action

Match on the exact string. Do not guess.

Two lines carry every code. The sign-in one is printed by the miner as it runs:

```
The browser sign-in did not complete (<code>)
```

and a capture Twitch refused is logged as `Twitch did not accept a captured login
context (<code>)`.

| Symptom | Cause | Action |
|---|---|---|
| `Cannot connect to Twitch` | timeouts too tight for the link | `quality 2`, then restart |
| single-digit `campaigns`, or `campaign discovery is not working` | the login cannot see the catalogue | [step 5](#step-5-signing-in) |
| `Unable to obtain a device code` | that client's device flow is closed — only reachable through `login device` | sign in with a browser instead, via [step 5](#step-5-signing-in) |
| `BROWSER_MISSING` | no Chromium-based browser on the miner | install one — see [step 6](#step-6-keep-the-login-alive) |
| `BROWSER_DISPLAY` | no display, and no `Xvfb` to stand in for one | `sudo apt install xvfb`, or the distribution's equivalent |
| `BROWSER_START` | the browser was found but would not start | on a minimal server, usually missing shared libraries; a snap or flatpak wrapper does this too |
| `BROWSER_PROTOCOL` | the browser stopped answering | retry `login browser`; if it repeats, report it |
| `bind_failed` | the port is already taken | another instance is probably running, or `login_server_port` collides — `netstat -ano \| findstr 8090` on Windows, `ss -ltnp \| grep 8090` on Linux |
| `LOGIN_TIMEOUT` | nobody finished signing in in time | retry when the user is ready |
| `LOGIN_CANCELLED` | cancelled from the page, or by `login cancel` | retry if that was not intended |
| `LOGIN_CLOSED` | the browser closed before the sign-in finished | retry |
| `ACCOUNT_MISMATCH` | that sign-in was for a different account than the miner is using | sign in as the account the miner already uses, or start from a clean `imported-session.json` to switch |
| log: `Twitch did not accept a captured login context: AUTH` / `IDENTITY` | the captured token did not validate | retry; if it repeats, report it |
| log: `Twitch did not accept a captured login context: CATALOG` | that context cannot read the catalogue | retry the sign-in |
| log: `Could not reach Twitch to check a captured login context` | the probe timed out | **not** a rejection — the sign-in keeps waiting and retries by itself |
| `The browser sign-in failed` with a traceback | an unexpected error | report the traceback |
| `renewal: unavailable - no session has been imported yet` | nothing has been captured | expected before step 5 |
| `renewal: unavailable - the imported session has no SDK cookie, so it cannot be renewed - sign in again` | the stored session predates renewal | sign in again |
| `renewal: unavailable - no Chromium-based browser was found on this machine` | no browser on the miner | install one, or `set renewal_browser_path …` |
| `renewal: unavailable - the stored SDK cookie has expired, so it cannot be renewed - sign in again` | the SDK cookie lapsed | sign in again |
| `renewal: unavailable - the renewal task is not running` | the renewal task is not active | report it |
| `The imported session stopped working (…)` | the proof expired and renewal did not keep up | it has already fallen back to `cookies.jar`; sign in again |
| `Login verification failure` at startup | the saved token is unusable | do **not** delete `cookies.jar`; report it, and sign in with a browser again |

These are the log strings, which is what `log/` contains. `login status` shows the
same reasons translated into the user's language.

## Things that are easy to get wrong

- **`0.0.0.0` is not connectable.** It is what the endpoint binds to.
- **The data directory follows the program file, not the shell's cwd.** See
  [Facts](#facts).
- **`--no-shell` does not mean "no login".** It only suppresses the prompt — with
  no session it will still open a browser, and on a host with no screen that
  means `Xvfb` has to be installed.
- **The browser has to run on the miner.** It cannot be pointed at the user's own
  browser: the session has to be born where it will be used.
- **Do not watch streams with the same Twitch account while mining.** Progress is
  counted per account and the two interfere.
- **The endpoint is a standing risk while it is open**, so it closes itself once a
  session is in. A later sign-in reopens it by itself - there is no command to
  turn it on, and none is needed.

## Reference

Full user-facing documentation:
[Getting started](docs/getting-started.md) · [中文](docs/getting-started.zh-CN.md).

Settings that matter for deployment, all settable with `set <key> <value>` and
persisted to `settings.json`:

| Key | Default | |
|---|---|---|
| `login_server_enabled` | `false` | serves the sign-in page; turned on by itself when a sign-in is asked for |
| `login_server_host` | `0.0.0.0` | bind address |
| `login_server_port` | `8090` | |
| `renewal_browser_path` | `""` | empty means auto-detect |
| `quality` | `1` | connection timeout multiplier; the `quality` command accepts `0..2` |
| `proxy` | empty | or set `https_proxy` in the environment |
| `language` | `en` | `zh-CN`, `zh-TW` and `en` are fully translated; other languages fall back to English for CLI text |
| `reload_interval` | `60` | minutes between inventory refreshes |

If you are changing the code rather than deploying it: the engine never imports
`cli` or `commands`, it only calls `self.gui.*`; register new commands in
`commands.py`'s `_register_builtins()`; run the test suites described in
`docs/getting-started.md`.
