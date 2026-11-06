# TwitchDropsMiner CLI

> 🌐 **English** · [中文](Home.zh-CN)

A headless, pure command-line build of
[TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner). It mines timed
Twitch drops by imitating "still watching" heartbeats at the GraphQL layer, so
**no video or audio is ever downloaded**. No GUI, no tray — it runs on a VPS, in
a container, over SSH, or on a Raspberry Pi.

## Start here

| | |
|---|---|
| 🚀 [Getting started](Getting-started) | install, first run, signing in with a browser, running it as a service |
| 🚀 [入门指南](Getting-started.zh-CN) | 上面那篇的中文版 |
| 📦 [Releases](https://github.com/LCBRST/TwitchDropsMiner-CLI/releases) | prebuilt binaries |
| 📖 [README](https://github.com/LCBRST/TwitchDropsMiner-CLI#readme) | the short version |

## Installing on Linux

One command — it installs the browser and `Xvfb`, builds from source, and cleans
the build environment up afterwards:

```
wget -O install_linux.sh https://raw.githubusercontent.com/LCBRST/TwitchDropsMiner-CLI/main/tools/install_linux.sh
chmod +x install_linux.sh && ./install_linux.sh
```

See [Getting started](Getting-started#install) for the prebuilt binary and the
source install. From a clone, the build and install scripts are in `tools/`
(`tools/build_cli.sh`, `tools\build.bat`).

## Web dashboard

The miner can serve a management page next to the mining loop, on all interfaces
so a phone or another computer on the LAN can open it:

```
api on        # :8091, prints the LAN address, generates a token
api open      # open the dashboard already signed in on this machine
api status    # show the LAN address to use from another device
```

It shows live drop and campaign progress, a drop-centric inventory, channels,
settings and logs. It can pause/resume mining, pick a channel, claim drops and
change settings. The Twitch sign-in panel is on its Settings page: start a
browser sign-in there and drive it in the embedded viewer (the page is proxied
through the dashboard's own port), or renew the imported session. Reward and
campaign artwork is cached locally and cleaned up when campaigns end.

Token authentication is on by default; `api token <your-token>` sets a custom
one, and `api auth off` disables it (only on a trusted network — the API can
control the miner). See [Getting started](Getting-started#web-dashboard).

## The one thing that trips people up

Twitch only lets some login types read the campaign catalogue, and the ones this
program can mint for itself no longer qualify. A session like that can still mine
whatever is already in progress, but it cannot discover new campaigns — you will
see only a handful of entries.

**`login browser`** starts a browser on the miner's own machine and keeps the
session it captures — one that can see everything. From then on the miner renews
it by itself.
See [Getting started](Getting-started#getting-the-full-campaign-list).

## Keeping it working

That session renews itself whenever Twitch's proof is about to lapse — sometimes
within the hour — using a headless browser on the machine running the miner. That
means **a Chromium-based browser has to be installed there** — Chrome, Chromium or
Edge — and `Xvfb` as well on a machine with no screen, for the browser window
signing in opens. Run `login status` to see the state, or `login renew` to force
one now.

See [Keeping the login alive](Getting-started#keeping-the-login-alive) for the
per-distribution install commands.

## Credentials

`cookies.jar` and `imported-session.json` are both credentials. Never commit,
share or sync them anywhere public — anyone holding them can act as your Twitch
account.

## Credits

- [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) — the
  original app and the entire mining engine.
- [rangermix/TwitchDropsMiner](https://github.com/rangermix/TwitchDropsMiner) —
  the integrity renewal design: replaying a captured session into a headless
  browser so Kasada's own script mints the next proof.

## License

MIT — © [DevilXD](https://github.com/DevilXD).
