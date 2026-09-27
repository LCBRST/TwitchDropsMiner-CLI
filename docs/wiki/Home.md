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
| 🚀 [Getting started](Getting-started) | install, first run, the login helper, running it as a service |
| 🚀 [入门指南](Getting-started.zh-CN) | 上面那篇的中文版 |
| 📦 [Releases](https://github.com/LCBRST/TwitchDropsMiner-CLI/releases) | prebuilt binaries |
| 📖 [README](https://github.com/LCBRST/TwitchDropsMiner-CLI#readme) | the short version |

## The one thing that trips people up

Twitch only lets some login types read the campaign catalogue, and the ones this
program can mint for itself no longer qualify. A session like that can still mine
whatever is already in progress, but it cannot discover new campaigns — you will
see only a handful of entries.

A small **login helper**, run once on a machine with Google Chrome, hands over a
session that can see everything. From then on the miner renews it by itself.
See [Getting started](Getting-started#getting-the-full-campaign-list).

## Keeping it working

That session renews itself roughly every 16 hours, using a headless browser on
the machine running the miner. No display is needed, but **a Chromium-based
browser has to be installed there** — Chrome, Chromium or Edge. Run `helper` to
see the state, or `helper renew` to force one now.

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
  the browser login helper and the integrity renewal design.

## License

MIT — © [DevilXD](https://github.com/DevilXD).
