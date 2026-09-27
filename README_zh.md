# TwitchDropsMiner CLI 中文说明

> 📖 [English](README.md) · 🚀 **[入门指南](docs/getting-started.zh-CN.md)**

[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) 的命令行分支。
不要 tkinter，不要系统托盘 —— 能跑 Python 的地方就能跑，所有操作都在一个交互式 shell 里完成。

<img width="1172" height="481" alt="TwitchDropsMiner CLI" src="https://github.com/user-attachments/assets/313e42e6-f1d0-4496-9ebd-8e554c8cdc41" />

## 这是什么

上游通过在 GraphQL 层伪造"正在观看"的心跳来挂限时掉宝，**全程不下载视频和音频**，省流量。
功能是没得说，但它的 GUI 在 VPS、Docker、SSH 里、树莓派上都很别扭。

这个分支把界面层换成了 CLI manager（`cli.py`）加命令 shell（`commands.py`），
挂机引擎一行没改。`gui.py` 原样保留：设个 `TDM_GUI=1` 就能切回上游界面。

- **为无界面环境而生** —— 服务器、容器、WSL、树莓派
- **能写进脚本** —— 加 `--no-shell` 就当服务或 cron 跑
- **状态看得见** —— 每次状态变化一行日志，`log` 随时往回翻
- **跟着上游走** —— 引擎代码零改动

## 功能

上游带来的：不占带宽的挂机、游戏优先级与排除列表、分片 WebSocket（同时跟踪约 199 个频道）、
自动发现活动、自动切换频道、持久化登录、自动领取、自动开始停止。

这个分支加的：交互式 shell，运行中随时改设置；`pause` / `resume` / `reload`；
手动指定频道；输出对管道友好；以及**浏览器登录助手** —— 拿回完整的活动列表，并且自动续签。

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

没有已保存的登录信息时，程序会让你走一次设备码登录（打印一个网址和一个短码，输一次即可），
登录信息存进 `cookies.jar`。然后：

```
priority add <游戏名>   # 想挂什么
resume                  # 开始
```

### 如果看不到活动

Twitch 只让部分登录类型看到活动目录，而程序自己能签发的那些已经不在其中了。
解决办法是**登录助手**：在一台有 Chrome 的机器上跑一次，把一份能看到完整目录的会话交给 miner，
之后 miner 会自动续签。

```
helper on     # 然后在桌面上对着打印出的地址跑 tdm-login-helper
helper        # 查看已导入的会话和续签状态
helper renew  # 不等它到期，立刻续一次
```

完整流程见 **[docs/getting-started.zh-CN.md](docs/getting-started.zh-CN.md)**。
自动续签需要 miner 那台机器上有个 Chromium 系浏览器 —— 不用显示器。

## 命令

`help` 列出全部，`help <命令>` 看某个命令怎么用。

| | |
|---|---|
| `status` `version` `log [N]` `clear` `exit` | 通用 |
| `whoami` `login` `helper [on\|off\|renew]` | 登录 |
| `pause` `resume` `reload` `watch <频道>` `unwatch` `claim` | 挂机控制 |
| `inventory`(`inv`) `campaigns` `drops` | 进度 |
| `channels [--all]` `online` | 频道 |
| `priority …` `exclude …` `mode …` `proxy …` `lang …` `quality …` `get`/`set` `save` | 设置 |
| `level <级别>` `dump [on\|off]` | 调试 |

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
| `imported-session.json` | 登录助手交付的会话 —— **同样是凭据** |
| `log/` | 按时间戳命名的日志和命令历史 |
| `lock.file` | 单实例锁 |

## 常见问题

- **连不上 Twitch** —— 默认超时给得紧，`quality 2` 调大。
- **走代理** —— 设 `https_proxy` 环境变量，或者用 `proxy` 命令。
- **别在挂机时用同一个账号看直播** —— 进度按账号算，两边会互相干扰。

更多见[指南](docs/getting-started.zh-CN.md#排错)。

## 致谢

- **[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)** ——
  原版程序，以及本分支跑着的整套挂机引擎。
- **[rangermix/TwitchDropsMiner](https://github.com/rangermix/TwitchDropsMiner)** ——
  浏览器登录助手和 integrity 续签方案；本项目做的是这套协议的 miner 一侧。

## 许可证

MIT，和上游一致 —— © [DevilXD](https://github.com/DevilXD)，详见 `LICENSE`。

## 贡献

欢迎 PR。新增命令在 `commands.py` 的 `_register_builtins()` 里注册，
再到[指南](docs/getting-started.zh-CN.md#命令一览)里补一行。
