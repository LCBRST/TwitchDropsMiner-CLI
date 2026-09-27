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
4. **Do not start the program interactively on a machine with a desktop unless
   the user expects it.** With no saved session it prints a device code and calls
   `webbrowser.open_new_tab`, which pops a browser window on the user's screen.
5. **Never invent, remember or copy the address for the login helper.** Read it
   from the miner's own `helper on` output. Every address in this file is an
   illustration (`192.0.2.0/24` is reserved for documentation), so none of them
   can be used as-is. `0.0.0.0` is a bind address and nothing can connect to
   it; see [step 5](#step-5-the-login-helper).
6. **Ask before enabling `helper_server_enabled` on a machine reachable from an
   untrusted network.** While it is on, anyone who can reach the port can install
   a Twitch session of their own choosing.
7. Do not modify `gui.py`, the engine in `twitch.py`, or `cookies.jar` handling to
   "make something work". Report the blocker instead.

## Facts

| | |
|---|---|
| Language / entry point | Python 3.10+, `main.py` |
| Runtime deps | `aiohttp`, `yarl`, `prompt_toolkit`, `truststore` |
| No display needed | yes, for everything except one optional step |
| **Data directory** | **the folder containing `main.py` (source) or the executable (build)** — not the current working directory |
| Files it creates there | `settings.json`, `cookies.jar`, `imported-session.json`, `lock.file`, `log/` |
| Listeners it opens | none by default; one TCP port only when the login helper is enabled |
| Release builds | Linux and Windows; **no macOS binary** |
| Upstream | DevilXD/TwitchDropsMiner (the mining engine) |
| Helper protocol | rangermix/TwitchDropsMiner (the login helper binary) |

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

Start it. Do this on a machine where a browser window is acceptable, or expect
the device code flow:

```bash
python main.py               # interactive shell
python main.py --no-shell    # no prompt, logs only — use this for a service
```

With no saved session it prints a URL and a short code, and asks the user to enter
the code at that URL. This is the *baseline* login. It is enough to mine, but it
will not see the full campaign catalogue — see step 4.

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

## Step 4: decide whether the login helper is needed

Read the campaign count:

```
campaigns
```

| What you see | Meaning | Action |
|---|---|---|
| Around a hundred or more | the login can see the catalogue | skip to [step 6](#step-6-keep-the-login-alive) |
| A handful - single digits, and they are the ones already in progress | **the login cannot see the catalogue** | do [step 5](#step-5-the-login-helper) |
| Log contains `campaign discovery is not working` | same as above | do [step 5](#step-5-the-login-helper) |

This is the single most common deployment problem, and it is not a bug.

Twitch gates the campaign catalogue on the client the login token was issued to.
The clients this program can log into by itself no longer qualify. Such a session
still mines whatever is already in progress, so the failure looks like a healthy
miner with a suspiciously short list.

## Step 5: the login helper

Only do this if the user can run something on a machine with **Google Chrome
installed**. If they cannot, stop here and tell them the campaign catalogue will
stay limited; do not attempt a workaround.

Three pieces, on two machines:

| Where | What |
|---|---|
| the miner | this program, with the helper endpoint enabled |
| the desktop with Chrome | the `tdm-login-helper` binary from [rangermix/TwitchDropsMiner releases](https://github.com/rangermix/TwitchDropsMiner/releases) — pick the archive matching **the desktop's** OS and CPU, not the miner's |

### 5a. Enable the endpoint on the miner

Set the setting, then restart the program (or run the command):

```
helper on
```

Expected:

```
login helper: enabled
listening on 0.0.0.0:8090
from another machine: http://192.0.2.10:8090
the helper runs on this machine: http://127.0.0.1:8090
run it where Chrome is installed: tdm-login-helper --tdm http://192.0.2.10:8090
```

**Hand the helper one of the `from another machine` addresses** (or `127.0.0.1`
when it runs on the miner itself). `listening on 0.0.0.0` is a bind address and
connecting to it fails with `SESSION_HELPER_NETWORK`.

When the host has several addresses — a VPN, a container bridge — all of them are
listed, with a line saying to use whichever the helper can reach. Do not assume
the first one is right, and do not skip that check on a multi-homed host.

Make sure the port is allowed through the firewall if the helper is on another
machine.

### 5b. Run the helper on the desktop

```bash
tdm-login-helper --tdm <miner-address>
```

The human signs into Twitch in the Chrome window it opens, including 2FA. The
helper then uploads the session and cleans up. Its temporary Chrome profile is
separate from the user's own.

### 5c. Confirm the import

```
helper
```

Expected, and effective immediately with no restart:

```
imported session: active, expires 2026-09-28 10:00:00
```

Then re-check `campaigns` — it should jump to the full catalogue.

## Step 6: keep the login alive

The imported session carries an integrity proof that expires in about 16 hours.
The miner renews it automatically a few minutes before that, by starting a
temporary headless Chromium on the miner's own machine.

Requirements and checks:

| | |
|---|---|
| Required | a Chromium-based browser on the **miner's** machine |
| Auto-detected | `chromium` / `chrome` on `PATH`, then platform install locations (including Edge on Windows) |
| Override | `set renewal_browser_path /path/to/chrome` |
| Status | the `helper` command shows `renewal: automatic, using …` or `renewal: unavailable - <reason>` |
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
`helper` and confirm it no longer says renewal is unavailable. Running as root is
handled: the browser is started with `--no-sandbox`, which Chromium requires in
that case.

Force one now instead of waiting out the 16 hours:

```
helper renew
```

Then re-run `helper` after ~15 seconds and look for a `last renewed:` line. The
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
- [ ] `helper` shows `imported session: active` (if step 5 was needed).
- [ ] `helper` shows `renewal: automatic` (if the user wants it to survive past
      16 hours).
- [ ] `log/` contains no repeating error.

## Failure and action

Match on the exact string. Do not guess.

Every error the login helper itself reports is printed as
`Login error code: SESSION_HELPER_<reason>` — grep for `SESSION_HELPER_` to find
it, and match the suffix below.

| Symptom | Cause | Action |
|---|---|---|
| `Cannot connect to Twitch` | timeouts too tight for the link | `quality 2`, then restart |
| single-digit `campaigns`, or `campaign discovery is not working` | the login cannot see the catalogue | [step 5](#step-5-the-login-helper) |
| `Unable to obtain a device code` | Twitch closed that client's device flow | switch `CLIENT_TYPE` in `constants.py` to another `ClientType` entry that still allows it, or use the helper |
| helper: `SESSION_HELPER_NETWORK` | cannot reach the miner | check `helper` says `enabled`; the port is listening (`ss -ltnp \| grep 8090` on Linux, `netstat -ano \| findstr 8090` on Windows); the address is one of the listed ones or `127.0.0.1`, **not** `0.0.0.0`; if the host has several, try each; firewall |
| helper: `SESSION_HELPER_DISABLED` | endpoint not enabled | `helper on` |
| helper: `SESSION_HELPER_CHROME_MISSING` | Chrome is not installed on the desktop | install Chrome there, or pass `--chrome <path>` to the helper |
| helper: `SESSION_HELPER_LOGIN_TIMEOUT` | nobody finished signing in before the ticket lapsed | run the helper again |
| helper: `SESSION_HELPER_EXPIRED` / `SESSION_HELPER_RESPONSE` | the ticket lapsed or the response was malformed | run the helper again |
| helper: `SESSION_HELPER_RESULT_UNKNOWN` | the network dropped after the session may have been installed | check `helper` in the miner **before** retrying — the session may already be in |
| helper: `SESSION_HELPER_REJECTED` | the miner refused the session | read the miner log for `Rejected an imported session: <code>` — see below |
| log: `Rejected an imported session: FORMAT/IDENTITY/AUTH` | the captured session did not validate | run the helper again; if it repeats, the capture is broken — report it |
| log: `Rejected an imported session: ACCOUNT_MISMATCH` | the helper signed into a different account than the miner is using | either run the helper against the same account, or delete `imported-session.json` and restart to switch |
| log: `Rejected an imported session: CATALOG` | that session cannot read the catalogue | run the helper again |
| `renewal: unavailable - no session has been imported yet` | nothing imported | expected before step 5 |
| `renewal: unavailable - the imported session has no SDK cookie, so it cannot be renewed - run the login helper again` | the stored session predates renewal | run the helper again |
| `renewal: unavailable - no Chromium-based browser was found on this machine` | no browser on the miner | install one, or `set renewal_browser_path …` |
| `renewal: unavailable - the stored SDK cookie has expired, so it cannot be renewed - run the login helper again` | the SDK cookie lapsed | run the helper again |
| `renewal: unavailable - the renewal task is not running` | the renewal task is not active | report it |

These are the log strings, which is what `log/` contains. The `helper`
command shows the same reasons translated into the user's language.

| `The imported session stopped working (…)` | the proof expired and renewal did not keep up | it has already fallen back to `cookies.jar`; run the helper again |
| `Login verification failure` at startup | the saved token is unusable | do **not** delete `cookies.jar`; report it, and use the helper to log in again |

## Things that are easy to get wrong

- **`0.0.0.0` is not connectable.** It is what the endpoint binds to.
- **The data directory follows the program file, not the shell's cwd.** See
  [Facts](#facts).
- **`--no-shell` does not mean "no login".** It only suppresses the prompt.
- **Do not run the helper on a machine without Chrome**, and do not run it over
  SSH into the miner — it must drive the desktop's own Chrome.
- **Do not watch streams with the same Twitch account while mining.** Progress is
  counted per account and the two interfere.
- **`helper server enabled` left on is a standing risk.** Turn it back off with
  `helper off` once the session is in.

## Reference

Full user-facing documentation:
[Getting started](docs/getting-started.md) · [中文](docs/getting-started.zh-CN.md).

Settings that matter for deployment, all settable with `set <key> <value>` and
persisted to `settings.json`:

| Key | Default | |
|---|---|---|
| `helper_server_enabled` | `false` | opens the login helper endpoint |
| `helper_server_host` | `0.0.0.0` | bind address |
| `helper_server_port` | `8090` | |
| `renewal_browser_path` | `""` | empty means auto-detect |
| `quality` | `1` | connection timeout multiplier; the `quality` command accepts `0..2` |
| `proxy` | empty | or set `https_proxy` in the environment |
| `language` | `en` | `zh-CN`, `zh-TW` and `en` are fully translated; other languages fall back to English for CLI text |
| `reload_interval` | `60` | minutes between inventory refreshes |

If you are changing the code rather than deploying it: the engine never imports
`cli` or `commands`, it only calls `self.gui.*`; register new commands in
`commands.py`'s `_register_builtins()`; run the test suites described in
`docs/getting-started.md`.
