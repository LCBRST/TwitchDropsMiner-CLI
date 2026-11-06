# TwitchDropsMiner CLI 中文说明

> 📖 [English](README.md) · 🚀 **[入门指南](docs/getting-started.zh-CN.md)**

[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) 的命令行分支。
不要 tkinter，不要系统托盘 —— 能跑 Python 的地方就能跑，所有操作都在一个交互式 shell 里完成。

<img width="1172" height="481" alt="TwitchDropsMiner CLI" src="https://github.com/user-attachments/assets/313e42e6-f1d0-4496-9ebd-8e554c8cdc41" />

## 这是什么

上游通过在 GraphQL 层伪造"正在观看"的心跳来挂限时掉宝，**全程不下载视频和音频**，省流量。
功能是没得说，但它的 GUI 在 VPS、Docker、SSH 里、树莓派上都很别扭。

这个分支把界面层换成了 CLI，挂机引擎保留。源码按功能分目录存放：
`twitchdropsminer/core/`（引擎）、`common/`（设置、翻译、工具）、`auth/`
（浏览器登录与续签）、`web/`（管理接口与图片缓存）、`cli/`（shell 与命令）。
`main.py` 是入口，构建/安装脚本在 `tools/`。

```
twitchdropsminer/
  common/   常量、设置、翻译、工具、异常、版本
  core/     Twitch 引擎、频道、库存、websocket
  auth/     浏览器登录、会话导入/续签、登录服务
  web/      管理接口、图片缓存
  cli/      CLIManager 与命令注册
main.py     入口
tools/      构建、安装、清理、网页同步脚本
```

- **为无界面环境而生** —— 服务器、容器、WSL、树莓派
- **能写进脚本** —— 加 `--no-shell` 就当服务或 cron 跑
- **状态看得见** —— 每次状态变化一行日志，`log` 随时往回翻
- **跟着上游走** —— 引擎代码零改动

## 功能

上游带来的：不占带宽的挂机、游戏优先级与排除列表、分片 WebSocket（同时跟踪约 199 个频道）、
自动发现活动、自动切换频道、持久化登录、自动领取、自动开始停止。

这个分支加的：交互式 shell，运行中随时改设置；`pause` / `resume` / `reload`；
手动指定频道；输出对管道友好；以及**自己起浏览器的登录** —— 拿回完整的活动列表，并且自动续签。

## 安装

**用现成的构建** —— 到 [Releases](https://github.com/LCBRST/TwitchDropsMiner-CLI/releases)
下载。只有两个构建：`TwitchDropsMiner-CLI_Linux` 和 `TwitchDropsMiner-CLI_Windows.exe`，
**没有 macOS 预构建**，Mac 请走源码安装。

```bash
chmod +x ./TwitchDropsMiner-CLI_Linux && ./TwitchDropsMiner-CLI_Linux   # Linux
```
```powershell
.\TwitchDropsMiner-CLI_Windows.exe                                     # Windows
```

**从源码** —— 需要 Python 3.10 以上，Linux / macOS / Windows 都行：

```bash
git clone https://github.com/LCBRST/TwitchDropsMiner-CLI.git
**Linux 一条命令** —— 装好浏览器和 `Xvfb`、从源码构建，然后把构建环境清理干净：

```bash
wget -O install_linux.sh https://raw.githubusercontent.com/LCBRST/TwitchDropsMiner-CLI/main/tools/install_linux.sh
chmod +x install_linux.sh && ./install_linux.sh
```

**从源码安装** —— Python 3.10 以上，Linux / macOS / Windows 都行：

```bash
git clone https://github.com/LCBRST/TwitchDropsMiner-CLI.git
cd TwitchDropsMiner-CLI
python3 -m venv venv
venv/bin/pip install -U pip wheel          # Windows 上是 venv\Scripts\pip
venv/bin/pip install -r requirements.txt
python main.py
```

## 运行

```bash
python main.py              # 交互式 shell
python main.py --no-shell   # 不给提示符，只打日志
```

没有已保存的登录信息时，miner 会自己起一个浏览器等你登录 —— 有显示器的机器上窗口就开在那里，
没有的话打印一个网址，从任何地方打开都能登。然后：

```
priority add <游戏名>   # 想挂什么
resume                  # 开始
```

### 如果看不到活动

Twitch 只让部分登录类型看到活动目录，而程序自己能签发的那些已经不在其中了。
**`login browser`** 会在 miner 本机起一个真浏览器，并留下它捕获到的会话 ——
这份会话能看到完整目录，之后 miner 会自动续签。

```
login browser  # 用 miner 自己起的浏览器登录
login status   # 查看已导入的会话和续签状态
login renew    # 不等它到期，立刻续一次
```

完整流程见 **[docs/getting-started.zh-CN.md](docs/getting-started.zh-CN.md)**。
登录和自动续签都需要 miner 那台机器上有个 Chromium 系浏览器 —— 不用显示器，
但无屏幕的机器还要装 `Xvfb` 给浏览器当屏幕。

## 命令

`help` 列出全部，`help <命令>` 看某个命令怎么用。

| | |
|---|---|
| `status` `version` `log [N]` `copy [N]` `clear` `exit` | 通用 |
| `whoami` `login [browser\|status\|cancel\|renew\|device\|doctor]` | 登录 |
| `pause` `resume` `reload` `watch <频道>` `unwatch` `claim` | 挂机控制 |
| `inventory`(`inv`) `campaigns` `drops` | 进度 |
| `channels [--all]` `online` | 频道 |
| `priority …` `exclude …` `mode …` `proxy …` `lang …` `quality …` `get`/`set` `save` | 设置 |
| `level <级别>` `dump [on\|off]` | 调试 |
| `api [status\|on\|off\|auth\|open\|copy\|file\|token\|rotate]` | 管理接口和网页控制台 |

## 网页控制台

矿工可以在挖宝的同时提供一个轻量管理页面。默认关闭；启用后监听所有网卡，
同一局域网里的手机或其他电脑也能打开：

```
api on        # 启动 :8091 并生成口令，同时打印局域网地址
api open      # 在本机直接打开已登录的控制台
api status    # 查看从其他设备访问要用的局域网地址
```

如果浏览器没有自动打开，`api copy` 会把口令复制到剪贴板，`api token` 则直接显示。
每个 `/api` 请求都要带这个口令。

SSH 下 `api copy` 和 `copy [N]` 使用终端自己的 OSC 52 剪贴板，远端机器不需要装
剪贴板工具。如果终端不支持 OSC 52，`copy [N]` 还会写一份 `copy.txt`，`api file`
会把口令写到可执行文件旁边的 `api-token.txt`（权限 600）——用 scp/SFTP 取回后
删掉即可。

页面里能看到实时的掉宝/活动进度、频道、设置和日志，也可以暂停/继续、切换
频道、领取掉宝和修改设置；还可以在网页里发起/取消浏览器登录、请求续签会话，
并**直接在页面里操作登录浏览器**——登录页面通过控制台自己的端口代理，不需要
再多转发 8090。`api token <口令>` 可以设置自定义管理口令，`api rotate` 则随机
生成一个。口令认证是可选项：`api auth off`（或 `set api_auth_enabled false`）
后网页会直接进入、不再要求口令；这等于把矿工交给任何能访问该端口的人，只建议
在可信网络里这样做。

掉宝奖励图和活动封面会缓存在 `cache/images/`，由控制台直接提供，不依赖 Twitch
CDN。活动从库存消失后，相关图片会自动删除；每次刷新库存以及每 30 分钟检查一次。

前端是独立项目
[TwitchDropMiner_WebAddon](https://github.com/LCBRST/TwitchDropMiner_WebAddon)，
HTTP 接口说明见它的 `API.md`。

接口可以控制矿工。虽然有口令保护，但在不完全信任的网络里，请把
`api_host` 设回 `127.0.0.1`，只在能拿到口令的人中间开放。

## 启动参数

| 参数 | |
|---|---|
| `-v` … `-vvvv` | 提高日志级别 |
| `--no-shell` | 不起提示符（当服务跑） |
| `--no-watchdog` | 关掉崩溃自动重启 |
| `--token <文件>` | 用文件里的 token 预填 `cookies.jar` |
| `--dump` | dump 每个 GQL 响应 |
| `--debug-ws` / `--debug-gql` | 调试 WebSocket / GQL |

默认开着看门狗，worker 崩了（包括 OOM、`kill -9`）会自动拉起来，每次重启记在
`log/restart.log`。正常退出不会重启。

## 文件

| | |
|---|---|
| `settings.json` | 全部设置 |
| `cookies.jar` | 保存的登录信息 —— **当密码对待** |
| `imported-session.json` | 从登录浏览器捕获的会话 —— **同样是凭据** |
| `log/` | 按时间戳命名的日志和命令历史 |
| `lock.file` | 单实例锁 |
| `cache/images/` | 控制台用的掉宝/活动图片缓存，可安全删除 |

## 常见问题

- **连不上 Twitch** —— 默认超时给得紧，`quality 2` 调大。
- **走代理** —— 用 `proxy <url>`；HTTP 请求和登录/续签浏览器都会使用它
  （浏览器不支持带用户名密码的代理）。
- **别在挂机时用同一个账号看直播** —— 进度按账号算，两边会互相干扰。

更多见[指南](docs/getting-started.zh-CN.md#排错)。

## 致谢

- **[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)** ——
  原版程序，以及本分支跑着的整套挂机引擎。
- **[rangermix/TwitchDropsMiner](https://github.com/rangermix/TwitchDropsMiner)** ——
  integrity 续签方案：把捕获到的会话重放进无头浏览器，让 Kasada 自己的脚本签下一份新证明。

## 许可证

MIT，和上游一致 —— © [DevilXD](https://github.com/DevilXD)，详见 `LICENSE`。

## 贡献

欢迎 PR。新增命令在 `twitchdropsminer/cli/commands.py` 的
`_register_builtins()` 里注册，
再到[指南](docs/getting-started.zh-CN.md#命令一览)里补一行。
