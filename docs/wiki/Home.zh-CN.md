# TwitchDropsMiner CLI

> 🌐 [English](Home) · **中文**

[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) 的命令行版本。
通过在 GraphQL 层伪造"正在观看"的心跳来挂限时掉宝，**全程不下载视频和音频**，省流量。
没有 GUI，没有系统托盘 —— VPS、容器、SSH 里、树莓派上都能跑。

## 从这里开始

| | |
|---|---|
| 🚀 [入门指南](Getting-started.zh-CN) | 安装、第一次运行、登录助手、当服务跑 |
| 🚀 [Getting started](Getting-started) | 上面那篇的英文版 |
| 📦 [Releases](https://github.com/LCBRST/TwitchDropsMiner-CLI/releases) | 现成的构建 |
| 📖 [README](https://github.com/LCBRST/TwitchDropsMiner-CLI#readme) | 简短版说明 |

## 唯一容易踩的坑

Twitch 只让部分登录类型看到活动列表，而程序自己能签发的那些已经不在其中了。这种会话
还能挂已经在进行中的掉宝，但发现不了新活动 —— 活动列表里只会剩寥寥几个。

解决办法是**登录助手**：在一台有 Chrome 的机器上跑一次，把一份能看到完整列表的会话交给 miner。
之后 miner 会自动续签。详见[入门指南](Getting-started.zh-CN#拿回完整活动列表)。

## 让它一直有效

那份会话会在证明快失效时自动续签（有时一小时内就要续一次），用的是**跑 miner 那台机器上**的无头浏览器。
不需要显示器，但那台机器**必须装有一个 Chromium 系浏览器** —— Chrome、Chromium 或 Edge。
执行 `helper` 看状态，或者 `helper renew` 立刻续一次。

各发行版怎么装，见[让登录保持有效](Getting-started.zh-CN#让登录保持有效)。

## 凭据

`cookies.jar` 和 `imported-session.json` 都是凭据。别提交、别外传、别往公网同步 ——
拿到这两个文件的人就能以你的 Twitch 账号身份操作。

## 致谢

- [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) ——
  原版程序，以及本分支跑着的整套挂机引擎。
- [rangermix/TwitchDropsMiner](https://github.com/rangermix/TwitchDropsMiner) ——
  浏览器登录助手和 integrity 续签方案。

## 许可证

MIT —— © [DevilXD](https://github.com/DevilXD)。
