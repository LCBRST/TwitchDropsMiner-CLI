# Wiki source

The guides live in `docs/`; this directory holds the wiki's front page and the
mapping used to publish them.

GitHub creates the wiki's git repository only once the first page has been
created in the browser, and there is no API for that. So the very first time:

1. Open <https://github.com/LCBRST/TwitchDropsMiner-CLI/wiki> and click
   **Create the first page**, save it with any placeholder text.
2. Publish from a checkout of this repository:

```bash
git clone https://github.com/LCBRST/TwitchDropsMiner-CLI.wiki.git wiki
cd wiki
cp ../docs/wiki/Home.md Home.md
cp ../docs/wiki/Home.zh-CN.md Home.zh-CN.md
cp ../docs/getting-started.md Getting-started.md
cp ../docs/getting-started.zh-CN.md Getting-started.zh-CN.md
git add . && git commit -m "docs: publish the getting started guide" && git push
```

After that, run the same copy/commit/push steps whenever the guides change.
