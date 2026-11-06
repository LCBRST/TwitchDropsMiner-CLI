# Vendored web dashboard

`index.html` and `assets/` in this directory are copied from
[LCBRST/TwitchDropMiner_WebAddon](https://github.com/LCBRST/TwitchDropMiner_WebAddon).
Do not edit them here — edit the add-on repository, then run:

```bash
tools/sync-webui.sh /path/to/TwitchDropMiner_WebAddon
```

`twitchdropsminer/web/api_server.py` serves this directory at `/`, and
`tools/build_cli.spec` bundles it into the single-file binary.
