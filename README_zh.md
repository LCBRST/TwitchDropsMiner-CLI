# TwitchDropsMiner CLI 中文版说明

> [DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner) 的纯命令行二次开发版。
> 不依赖 tkinter，不依赖系统托盘——只要能跑 Python 就能用（服务器、容器、
> WSL、无显示器的盒子），通过交互式命令 shell 控制所有功能。

## 预览
<img width="1172" height="481" alt="cn" src="https://github.com/user-attachments/assets/313e42e6-f1d0-4496-9ebd-8e554c8cdc41" />


---

## 这是什么

原版 TwitchDropsMiner 是个 Windows/Linux 桌面应用（tkinter GUI + 系统托盘），
通过在 GraphQL 层伪造"正在观看"心跳来 AFK 挂掉 Twitch 的限时挂宝——完全不
下载流媒体数据。功能很好，但 GUI 不适合无界面服务器、Docker、SSH-only 环境
或纯终端工作流。

这个分支保留了完整的挂宝引擎（GQL 管线、WebSocket 分片、掉宝跟踪、频道切换），
把 GUI 层换成：

- **CLI manager**（`cli.py`）—— 模拟 GUI 接口
- **交互式命令 shell**（`commands.py`）—— 用命令控制
- 更精简的入口（`main.py`）—— 不要 Tk，不要弹窗

原 `gui.py` 完全没动。设置环境变量 `TDM_GUI=1` 仍能切回原版 GUI。

## 为什么做这个

- **无头环境** —— 在 VPS / Docker / WSL / Raspberry Pi 上跑得动
- **可脚本化** —— `--no-shell` 用于 cron / 后台守护
- **可观测** —— 每次状态切换都打一行日志；`log` 命令随时翻最近日志


## 功能

继承自上游：

- 无流量挂机（不下视频音频）
- 游戏优先级和排除列表
- 分片 WebSocket 连接（最多约 199 个频道同时跟踪）
- 根据已绑定账号自动发现活动
- 流标签 / 挂宝活动校验
- 主播下播或更高优先级主播开播时自动切频道
- 通过 `cookies.jar` 持久化登录
- 完成的挂宝自动领取
- 新活动出现时自动开始挂宝，最后一个挂宝完成后后自动停止

本分支新增：

- **OAuth Device Code 登录** —— 打印一个 URL + 6–8 位 code，浏览器登录即可。
  终端里不会让你输密码 / 2FA。Token 存在 `cookies.jar` 里，登录一次即可。
- **交互式命令 shell** —— `help` 看所有命令。
- **运行时改设置** —— 不重启就能改 priority、exclude、mode、proxy、语言、
  连接质量等。
- **`reload` / `pause` / `resume`** —— 不退出进程也能重置客户端或暂停挖矿。
- **手动选频道** —— `watch <login>` 强制切换。
- **管道友好的输出** —— 检测到 stdout 不是 TTY 时自动跳过 ANSI 控制符。

## 安装与运行

### 从构建好的版本安装
1.从release下载最新的可执行文件
2.赋予权限 chmod +777 ./twitch-drops-miner-cli

### 运行
./twitch-drops-miner-cli


### 手动方法
要求 Python 3.10+，Linux/macOS/Windows（只在 Linux 上测过）。

```bash
git clone https://github.com/LCBRST/TwitchDropsMiner-CLI.git
cd TwitchDropsMiner-CLI
python3 -m venv venv
venv/bin/pip install -U pip wheel
venv/bin/pip install -r requirements.txt
```

`requirements.txt` 里那些 GUI 依赖（`Pillow`、`pystray`、`PyGObject`）
是给上游 GUI 构建用的，CLI 模式下用不上但仍会被装上。



### 运行

```bash
python main.py            # 交互式 shell
python main.py --no-shell # 守护模式，无提示符，只有日志
```

第一次运行时会打印 Twitch device-code 激活页 URL 和一个 8 位 code。
打开链接，填进去，授权。Token 会存到 `cookies.jar`，之后启动就不用再登了。

### 启动参数

| 参数 | 说明 |
| --- | --- |
| `--version` | 显示版本并退出 |
| `-v` / `-vv` / `-vvv` / `-vvvv` | 提高日志级别 |
| `--log` | （兼容保留）日志现在默认写入 `log/<时间戳>.log`，无需此参数 |
| `--dump` | 把每个 GQL 响应 dump 到 `dump.dat` |
| `--no-shell` | 不启动交互式提示符（后台模式） |
| `--no-watchdog` | 关闭崩溃自动重启（默认开启看门狗） |
| `--token <文件>` | 用文件里的 OAuth token 预填 `cookies.jar` |
| `--debug-ws` | （调试）WebSocket 帧打到 DEBUG |
| `--debug-gql` | （调试）GQL 请求打到 DEBUG |

### 崩溃自动重启（看门狗）

默认开启：程序启动时会拉起一个轻量看门狗父进程来监督真正干活的子进程，
子进程一旦崩溃（包括被 OOM / `kill -9` 直接杀死）会自动重启。每次重启都会在
`log/restart.log` 里记一行。正常退出（`exit` 命令 / Ctrl+C）不会重启。

- 关掉它：加 `--no-watchdog`（例如你自己用 systemd 等外部守护时）。
- 停止整个程序：Ctrl+C，或杀掉看门狗父进程（`pkill -f TwitchDropsMiner`）。

环境变量 `TDM_GUI=1` → 切回原版 GUI。

## 命令

`help` 看完整列表，`help <命令>` 看某个命令的用法。

### 通用

| 命令 | 作用 |
| --- | --- |
| `help [cmd]` | 命令列表，或某个命令的详细帮助 |
| `status` | 显示引擎状态、当前观看频道、ws 状态、登录情况 |
| `version` | 显示版本 |
| `log [N]` | 翻最近 N 行日志（默认 20） |
| `clear` | 清屏 |
| `exit` / `quit` / `q` | 退出 |

### 登录

| 命令 | 作用 |
| --- | --- |
| `whoami` | 显示登录状态和 Twitch user id |
| `login` | （提示）说明如何强制重新登录 |

### 挖矿控制

| 命令 | 作用 |
| --- | --- |
| `pause` | 停止观看，引擎进入 IDLE |
| `resume` | 重新拉取库存，开始挖 |
| `reload` | 整个客户端重新初始化 |
| `watch <login>` | 强制切到某个已知频道 |
| `unwatch` | 停止观看当前频道 |
| `claim` | 立即强制领取所有可领取的掉宝 |

### 库存

| 命令 | 作用 |
| --- | --- |
| `inventory`（别名 `inv`） | 列出所有活动和每个掉宝的进度 |
| `campaigns` | 只列活动 |
| `drops` | 当前正在挂的掉宝进度 |

### 频道

| 命令 | 作用 |
| --- | --- |
| `channels [--all]` | 已知频道列表（默认只显示在线的） |
| `online` | 仅显示在线频道 |

### 设置（持久化到 `settings.json`）

| 命令 | 作用 |
| --- | --- |
| `priority list \| add <游戏> \| remove <游戏> \| move <游戏> <增量> \| clear` | 管理优先级列表 |
| `exclude list \| add <游戏> \| remove <游戏> \| clear` | 管理排除列表 |
| `mode [priority_only \| ending_soonest \| low_avbl_first]` | 查看或设置优先级模式 |
| `proxy [<url> \| clear]` | HTTP 代理 |
| `lang [code]` | 界面语言 |
| `quality [0..2]` | 连接超时倍数（代理慢就调高） |
| `get [key]` / `set <key> <value>` | 通用读写 |
| `save` | 立即写盘 |

### 调试

| 命令 | 作用 |
| --- | --- |
| `level <DEBUG\|INFO\|WARNING\|ERROR\|CRITICAL>` | 运行时改日志级别 |
| `dump [on\|off]` | 切换 GQL 响应 dump |

### 优先级模式说明

| 模式 | 行为 |
| --- | --- |
| `priority_only` | 只挖 priority 列表里的游戏（默认） |
| `ending_soonest` | priority 之外的游戏按"快结束"排序 |
| `low_avbl_first` | priority 之外的游戏按"剩余库存最少"排序 |

## 文件位置

所有文件都在项目根目录。

| 文件 | 用途 |
| --- | --- |
| `settings.json` | 持久化设置（priority、exclude、mode、proxy、lang、quality 等） |
| `cookies.jar` | 持久化登录。请像对待密码一样对待这个文件——拿到它的人就能用你的 Twitch 账号 |
| `lock.file` | 单实例锁。崩溃后会留下，可手动删 |
| `log/` | 自动生成：时间戳命名的日志（`YYYY-MM-DD_HH-MM-SS.log`，轮转）+ 命令历史 `history` |
| `cache/` | GUI 模式才用的图片缓存，CLI 模式不创建 |

## 架构

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

引擎从不直接 import `cli` 或 `commands`，只调用 `self.gui.*`。CLIManager
完整复刻了引擎用到的所有方法（`tray.change_icon`、`status.update`、
`channels.set_watching/clear/display`、`progress.display`、`inv.add_campaign`、
`websockets.update`、`login.ask_login`、`login.ask_enter_code`、`set_games`、
`display_drop`、`clear_drop`、`print`、`save`、`start`、`stop`、`close`、
`close_window`、`prevent_close`、`grab_attention`、`coro_unless_closed`、
`wait_until_closed`、`running`、`close_requested`）。

## 常见问题

### "Cannot connect to Twitch"（连接超时）

默认超时比较紧（连接 5 秒、整体 10 秒），在慢网络、透明代理（fake-IP）或者
首次 TLS 握手时常常不够。把倍数调大：

```
tdm[idle]> quality 2
```

`quality` 是 1–6 的乘数，会同时放大两个超时。会持久化。

### 走代理

aiohttp 现在 (`trust_env=True`) 会自动读 `http_proxy` / `https_proxy` /
`no_proxy` 环境变量：

```bash
export https_proxy=http://127.0.0.1:7890
python main.py
```

或者在 shell 里设：

```
tdm[idle]> proxy http://127.0.0.1:7890
```

如果代理在软路由上做透明代理（fake-IP + tproxy），通常什么都不用配；如果
依然连不上，先把 `quality` 调到 2 或 3。

### 不要在挖矿时用同账号看流

Twitch 的掉宝进度是按账号统计的。同时挂宝+看流会让进度上报错乱、卡在
当前掉宝。

### `cookies.jar` 当作敏感凭据

不要分享、不要 commit、不要同步到公网。任何拿到这个文件的人都能用你的
Twitch 账号操作。

## 许可证

本分支沿用 MIT 协议，与上游一致。原版权归
[DevilXD](https://github.com/DevilXD)，详见上游 `LICENSE`。

## 贡献

欢迎 PR。新增命令时记得在
`commands.py` 的 `_register_builtins` 里注册，并在本文档加一行说明。
