# TwitchDropsMiner CLI (English)

> 📖 **中文说明 / Chinese documentation:** [**README_zh.md**](README_zh.md)

> A headless, pure‑CLI fork of [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner).  
> No tkinter, no system tray — runs wherever Python runs (servers, containers,  
> WSL, headless boxes), controlled via an interactive command shell.

After startup you’ll see the prompt `tdm[idle]>`.  
Type `help` to list all available commands.

```
$ python main.py
[09:38:00] 
[09:38:00]   TwitchDropsMiner v16.dev (CLI)
[09:38:00] 
[09:38:01] [login] Logging in...
[09:38:02] 
[09:38:02] Twitch login required (Device Code flow)
[09:38:02]   1. Open: https://www.twitch.tv/activate?device-code=ABCDEFGH
[09:38:02]   2. Enter the code: ABCDEFGH
[09:38:02]   3. Approve the login in your browser, then come back.
[09:38:02] 
tdm[idle]> priority add "Escape from Tarkov"
tdm[idle]> mode priority_only
tdm[idle]> resume
tdm[active]> status
```

---

## What this is

The original TwitchDropsMiner is a desktop application (tkinter GUI + system tray)  
that AFK‑mines Twitch drops by faking “watching” heartbeats at the GraphQL layer —  
**without downloading any video or audio streams**.

It works well, but the GUI makes it hard to use on:

- headless servers
- Docker containers
- WSL / Raspberry Pi
- SSH‑only environments
- pure‑terminal workflows

This branch keeps the **entire mining engine** intact  
(GQL pipeline, WebSocket sharding, drop tracking, automatic channel switching),  
and replaces the GUI layer with:

- **CLI manager** (`cli.py`) — implements the same interface the engine expects
- **Interactive command shell** (`commands.py`) — control everything by typing
- **Minimal entry point** (`main.py`) — no Tk, no popups, no tray icon

The original `gui.py` is **completely untouched**.  
Set `TDM_GUI=1` to switch back to the upstream tkinter GUI at any time.

---

## Why this exists

- **Headless‑first** — runs on VPS / Docker / WSL / Pi
- **Scriptable** — use `--no-shell` for cron jobs or background daemons
- **Observable** — every state change prints one clean log line
- **Upstream‑friendly** — engine code is unmodified

---

## Features

### Inherited from upstream

- Zero‑bandwidth mining (no video/audio downloaded)
- Game priority & exclusion lists
- Sharded WebSocket connections (~199 channels)
- Automatic campaign discovery
- Stream tag & drop campaign validation
- Auto‑switch channels
- Persistent login via `cookies.jar`
- Auto‑claim completed drops
- Auto start/stop on campaign changes

### Added in this fork

- **OAuth Device Code login**
- **Interactive command shell**
- **Live configuration changes**
- **`reload` / `pause` / `resume`**
- **Manual channel selection**
- **Pipe‑friendly output**

---

## Installation & Running

### Using prebuilt binaries
1.Download bin file at release

```
chmod +x ./twitch-drops-miner-cli
./twitch-drops-miner-cli
```

### Manual installation

```
git clone https://github.com/<your-fork>/TwitchDropsMiner-CLI.git
cd TwitchDropsMiner-CLI
python3 -m venv venv
venv/bin/pip install -U pip wheel
venv/bin/pip install -r requirements.txt
```

Minimal CLI dependencies:


aiohttp>=3.9,<4.0
yarl
truststore


---

## Running

```
python main.py                # interactive shell
python main.py --no-shell     # daemon mode
TDM_GUI=1 python main.py      # original GUI
```

---

## CLI arguments

| Argument | Description |
|--------|------------|
| `--version` | Show version |
| `-v` … `-vvvv` | Increase log verbosity |
| `--log` | Write logs to `log.txt` |
| `--dump` | Dump GQL responses |
| `--no-shell` | Background mode |
| `--token <file>` | Pre‑seed login token |
| `--debug-ws` | Debug WebSocket frames |
| `--debug-gql` | Debug GQL requests |

---

## Commands

### General

| Command | Purpose |
|--------|--------|
| `help [cmd]` | Show help |
| `status` | Show engine status |
| `version` | Show version |
| `log [N]` | Show recent logs |
| `clear` | Clear screen |
| `exit` / `quit` / `q` | Exit |

### Login

| Command | Purpose |
|--------|--------|
| `whoami` | Show login status |
| `login` | Force re‑login instructions |

### Mining control

| Command | Purpose |
|--------|--------|
| `pause` | Pause mining |
| `resume` | Resume mining |
| `reload` | Restart client |
| `watch <login>` | Force channel |
| `unwatch` | Stop watching |
| `claim` | Claim all drops |

### Inventory

| Command | Purpose |
|--------|--------|
| `inventory` / `inv` | Campaigns + drops |
| `campaigns` | Campaigns only |
| `drops` | Active drop progress |

### Channels

| Command | Purpose |
|--------|--------|
| `channels [--all]` | Known channels |
| `online` | Online channels |

### Settings

| Command | Purpose |
|--------|--------|
| `priority ...` | Manage priority list |
| `exclude ...` | Manage exclusion list |
| `mode [...]` | Set priority mode |
| `proxy [...]` | Set HTTP proxy |
| `lang [code]` | UI language |
| `quality [0..2]` | Timeout multiplier |
| `get / set` | Config access |
| `save` | Save settings |

### Debug

| Command | Purpose |
|--------|--------|
| `level <LEVEL>` | Change log level |
| `dump [on|off]` | Toggle GQL dump |

---

## Files

| File | Purpose |
|----|--------|
| `settings.json` | Persistent settings |
| `cookies.jar` | Login token (**keep secret**) |
| `lock.file` | Single‑instance lock |
| `log.txt` | Logs |
| `cache/` | GUI cache (unused in CLI) |

---

## Architecture
```
              +---------------------+        +-----------------------+
              |  twitch.py 引擎     |  调用  |   gui 接口           |
              | (状态机、GQL、       +------->|   (tray, status,     |
              |  websockets)        |        |    channels, inv,    |
              +----------+----------+        |    progress, login)  |
                         |                   +----------+-----------+
                         | self.gui = ...               |
                         |                              |
              +----------v----------+        +----------v-----------+
              |  cli.CLIManager     |        |  gui.GUIManager      |
              |  （默认）           |  XOR   |  (TDM_GUI=1)         |
              |                     |        |                      |
              |  + 交互式 shell    |        |  + tk/pystray 控件    |
              +----------+----------+        +----------------------+
                         |
              +----------v----------+
              |  commands.py        |
              |  CommandRegistry    |
              +---------------------+
```

---

## Common issues

### Cannot connect to Twitch


`tdm[idle]> quality 2`


### Proxy


`export https_proxy=http://127.0.0.1:7890`


or:


`tdm[idle]> proxy http://127.0.0.1:7890`


### Do NOT watch streams while mining

Twitch tracks drops per account — watching while mining breaks progress.

### `cookies.jar` is a credential

Treat it like a password. Never commit or share it.

---

## License

MIT — © [DevilXD](https://github.com/DevilXD)

---

## Contributing

PRs welcome. Register new commands in `_register_builtins()` and update docs.
