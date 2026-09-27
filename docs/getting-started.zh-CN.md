# 入门指南

从装好到跑起来，全程不需要桌面环境。

- [这是什么](#这是什么)
- [环境要求](#环境要求)
- [安装](#安装)
- [第一次运行](#第一次运行)
- [拿回完整活动列表](#拿回完整活动列表)
- [让登录保持有效](#让登录保持有效)
- [日常使用](#日常使用)
- [命令一览](#命令一览)
- [文件](#文件)
- [作为服务运行](#作为服务运行)
- [排错](#排错)
- [内部结构](#内部结构)
- [致谢](#致谢)

---

## 这是什么

TwitchDropsMiner 的命令行版本。上游通过在 GraphQL 层伪造"正在观看"的心跳来挂限时掉宝，
**全程不下载任何视频和音频**，省流量。原版带 GUI 和系统托盘，在 VPS、容器、SSH 里用起来很别扭；
这个分支把界面层换成了交互式 shell。

挂机引擎用的还是上游那套，一行没改。

## 环境要求

| | |
|---|---|
| Python | 3.10 以上（源码安装） |
| 系统 | Linux / macOS / Windows，**不需要显示器** |
| 网络 | 能出站访问 `twitch.tv`、`gql.twitch.tv`、`spade.twitch.tv` 的 HTTPS |
| 浏览器 | 只有自动续签需要，见[让登录保持有效](#让登录保持有效) |

挂机时内存占用约 65 MB，带宽方面除了 API 请求本身没有额外开销。

## 安装

### 用现成的构建

[Releases](https://github.com/LCBRST/TwitchDropsMiner-CLI/releases) 里只有两个构建：
`TwitchDropsMiner-CLI_Linux` 和 `TwitchDropsMiner-CLI_Windows.exe`。**没有 macOS 预构建**，
Mac 请用下面的源码安装。

```bash
chmod +x ./TwitchDropsMiner-CLI_Linux && ./TwitchDropsMiner-CLI_Linux   # Linux
```
```powershell
.\TwitchDropsMiner-CLI_Windows.exe                                     # Windows
```

### 从源码安装

```bash
git clone https://github.com/LCBRST/TwitchDropsMiner-CLI.git
cd TwitchDropsMiner-CLI
python3 -m venv venv
venv/bin/pip install -U pip wheel          # Windows 上是 venv\Scripts\pip
venv/bin/pip install -r requirements.txt
python main.py
```

`requirements.txt` 里还列了 GUI 依赖（`Pillow`、`pystray`），那是给上游桌面版构建用的，
这里用不上。想装得干净点，只装 `aiohttp yarl prompt_toolkit truststore` 就行。

## 第一次运行

```bash
python main.py              # 交互式 shell
python main.py --no-shell   # 不给提示符，只打日志（当服务跑）
```

没有已保存的登录信息时，程序会让你走一次**设备码登录**：终端打印一个网址和一个短码，
你在浏览器里输一次就行。登录信息存进 `cookies.jar`，以后不用再登。

登录完就可以开始挂机了：

```
priority add <游戏名>   # 把想挂的游戏加进优先列表
mode priority_only      # 只挂优先列表里的（默认就是这个模式）
resume                  # 开始
```

`help` 列出全部命令，`help <命令>` 看某个命令怎么用。

## 拿回完整活动列表

**`campaigns` 只列出寥寥几个活动，或者日志里出现 `campaign discovery is not working` 的话，
就是这里说的情况。**

Twitch 按**当初签发这个登录 token 的客户端**决定能看到哪些活动。而程序现在能自己签发的几种
客户端，全都被 Twitch 关掉了目录权限 —— 这种会话还能继续挂已经在进行中的掉宝，但**看不到新活动**。

解决办法是**登录助手**：一个跑在装有 Chrome 的电脑上的小程序。它打开 Chrome 让你正常登录一次，
然后把浏览器那边的会话（这种能看到完整目录）交给 miner。

只有在 miner 提示需要，或者发现活动不全的时候才需要做这一步。

### 1. 打开接收端口

在 miner 的 shell 里：

```
helper on
```

输出大概长这样：

```
login helper: enabled
listening on 0.0.0.0:8090
from another machine: http://192.0.2.10:8090
the helper runs on this machine: http://127.0.0.1:8090
run it where Chrome is installed: tdm-login-helper --tdm http://192.0.2.10:8090
```

`0.0.0.0` 是**监听**地址，连不上它。助手在别的机器上，就用"从别的机器连"那行的地址；
助手和 miner 在同一台机器上，用 `127.0.0.1` 那条。

**miner 有多个地址时**（比如同时有 VPN、Docker 网桥），它们会全部列出来，并提示你用助手那边
能连通的那个。

**上面那些地址只是示例**，要用你自己 miner 打印出来的。`192.0.2.x` 是保留给文档的地址段，
永远不会是你的机器。

跨机器连的话记得在防火墙上放行这个端口。

### 2. 运行助手

到 [rangermix/TwitchDropsMiner 的 release](https://github.com/rangermix/TwitchDropsMiner/releases)
下载登录助手 —— 注意选**桌面那台机器**的系统和 CPU，不是 miner 的。

```bash
tdm-login-helper --tdm <miner 地址>
```

在它弹出的 Chrome 窗口里正常登录 Twitch（该输 2FA 就输），等它提示成功。之后它会关掉 Chrome、
删掉临时配置目录，**不会碰你平时用的 Chrome 配置**。

### 3. 确认一下

```
helper
```

这时应该显示 `imported session: active, expires ...`，miner 里的活动数量也会变成完整的。
**立刻生效，不用重启。**

## 让登录保持有效

导入的会话里带一份 integrity 证明，大约 16 小时后失效。miner 会自动续：到期前几分钟，
它临时起一个**无头 Chromium**，把捕获到的会话重放进去，让页面自己重新签一份证明，
验证通过之后才拿它替换旧的。

**前提是跑 miner 的机器上得有一个 Chromium 系浏览器**，除此之外对机器没有别的要求 ——
不用显示器，也不用桌面环境。

- 查找顺序：`PATH` 里的 `chromium` / `chrome`，然后是各平台的默认安装位置（Windows 上还会找 Edge）。
- 想指定具体某个：

  ```
  set renewal_browser_path C:\Program Files\Google\Chrome\Application\chrome.exe
  set renewal_browser_path /usr/bin/google-chrome      # Linux 和 macOS
  ```

- `helper` 会显示续签状态：`renewal: automatic, using ...`，或者 `renewal: unavailable - <原因>`。

不想等 16 小时，可以手动触发一次：

```
helper renew
```

续签一直失败也不会把程序搞坏：它会退避重试，期间照常使用当前会话；等会话真过期了，
自动退回 `cookies.jar`。那时候重新跑一次助手登录即可。

### Linux 上怎么装浏览器

> **Ubuntu 20.04 及更新的版本上，不要用 `apt install chromium`。** 那装出来的是 snap 包装，
> 基本没法这么用。flatpak 也一样。

| 发行版 | |
|---|---|
| Debian / Ubuntu | 用 Google Chrome 的 `.deb`：<br>`wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb`<br>`sudo apt install ./google-chrome-stable_current_amd64.deb`<br>ARM 机器把文件名换成 `..._current_arm64.deb` |
| Fedora / RHEL | `sudo dnf install https://dl.google.com/linux/direct/google-chrome-stable_current_x86_64.rpm` |
| Debian 本家 | `sudo apt install chromium` —— 这里是**真正的包**，跟 Ubuntu 不一样 |
| Arch | `sudo pacman -S chromium` |
| Alpine / 容器 | `apk add chromium` |
| 完全没有 root | `pip install playwright && playwright install chromium` —— 把 Chromium 装在你自己的家目录里，不需要任何系统包 |

装完验一下：`google-chrome --version`（或 `chromium --version`）能打印版本号，
然后 `helper` 里的续签状态应该变成 `renewal: automatic, using …`。

以 root 运行的情况（比如在容器里）已经处理好了：会自动加 `--no-sandbox`，
这是 Chromium 在那种环境下所要求的。

## 日常使用

| | |
|---|---|
| 看当前情况 | `status`、`drops`、`inventory` |
| 改挂什么 | `priority ...`、`exclude ...` |
| 暂停但别退出 | `pause` / `resume` |
| 手动指定频道 | `watch <频道>` / `unwatch` |
| 强制刷新一遍 | `reload` |
| 看登录状态 | `whoami`、`helper` |

## 命令一览

`help` 会列出全部，这里是完整的一份。

**通用** —— `help [命令]`、`status`、`version`、`log [N]`、`clear`、
`exit` / `quit` / `q`

**登录** —— `whoami`、`login`、`helper [on|off|renew]`

**挂机控制** —— `pause`、`resume`、`reload`、`watch <频道登录名>`、`unwatch`、`claim`

**进度** —— `inventory`（别名 `inv`）、`campaigns`、`drops`

**频道** —— `channels [--all]`、`online`

**设置** —— 下面这些都会写进 `settings.json`：

| 命令 | |
|---|---|
| `priority list \| add <游戏> \| remove <游戏> \| move <游戏> <增量> \| clear` | 优先挂哪些游戏 |
| `exclude list \| add <游戏> \| remove <游戏> \| clear` | 哪些游戏永远不挂 |
| `mode [priority_only \| ending_soonest \| low_avbl_first]` | 优先列表里没得挂时挂什么 |
| `proxy [<url> \| clear]` | HTTP 代理 |
| `lang [code]` | 界面语言 |
| `quality [0..2]` | 连接超时倍数，网络慢就调高 |
| `get [键]` / `set <键> <值>` | 读写任意一项设置 |
| `save` | 立即写盘 |

**调试** —— `level <级别>`、`dump [on|off]`

## 文件

都在可执行文件旁边（源码安装的话就是仓库根目录）。

| 文件 | |
|---|---|
| `settings.json` | 全部设置 |
| `cookies.jar` | 保存的登录信息 —— **当密码对待** |
| `imported-session.json` | 登录助手交付的会话 —— **同样是凭据** |
| `lock.file` | 单实例锁，崩溃后可以手动删掉 |
| `log/` | 按时间戳命名的日志，以及命令历史 |

想迁移到别的机器，把 `cookies.jar` 和 `imported-session.json` 一起带走就行。
两个都是凭据，别外传，更别提交到仓库。

## 作为服务运行

加 `--no-shell` 就不会起交互提示符，适合交给守护进程管理。程序自带看门狗，worker 崩了会自己
拉起来，所以**交给外部 supervisor 时要加 `--no-watchdog`**，不然两边会打架。

**Linux（systemd）：**

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

**Windows（任务计划程序）：** 在管理员命令提示符里执行，路径按实际改；用 `pythonw.exe`
可以不弹控制台窗口：

```powershell
schtasks /create /tn TwitchDropsMiner /sc onstart /ru %USERNAME% ^
  /tr "C:\tdm\venv\Scripts\pythonw.exe C:\tdm\main.py --no-shell --no-watchdog"
```

路径里有空格的话引号还要再套一层；想让它像真正的服务那样失败自动重启，用
[NSSM](https://nssm.cc/) 更省事。

**macOS（launchd）：** 写个带 `RunAtLoad` 和 `KeepAlive` 的 LaunchAgent，跑同一条命令。

三个平台上，关掉控制台窗口都会把它杀掉，所以要交给 supervisor 而不是手动开着。

## 排错

**看不到活动，或者只有几个。** 这个登录读不到完整目录 —— 见[拿回完整活动列表](#拿回完整活动列表)。

**提示 `Cannot connect to Twitch`。** 默认超时给得比较紧，调大一点：

```
quality 2
```

走代理的话，设环境变量 `https_proxy`，或者用 `proxy http://127.0.0.1:7890`。
软路由上那种透明代理通常什么都不用配，把 `quality` 调高基本就够。

**助手报 `SESSION_HELPER_NETWORK`。** 连不上 miner。依次检查：`helper` 里显示 `enabled` 了吗；
端口在监听吗（Linux 上 `ss -ltnp | grep 8090`，Windows 上 `netstat -ano | findstr 8090`）；
地址用的是 `127.0.0.1` 而不是 `0.0.0.0` 吗；防火墙放行了吗。

**助手报 `SESSION_HELPER_REJECTED`。** miner 拒了这个会话，日志里的
`Rejected an imported session: <码>` 会写明原因：

| 码 | |
|---|---|
| `FORMAT` / `IDENTITY` / `AUTH` | 捕获到的会话没通过校验 |
| `ACCOUNT_MISMATCH` | 助手登录的账号和 miner 当前用的不是同一个 |
| `CATALOG` | 这个会话读不到活动列表 |

**续签显示不可用。** 看 `helper` 输出里的原因。最常见的是没找到 Chromium 系浏览器
—— 见[让登录保持有效](#让登录保持有效)。

**续签报 `BROWSER_START`。** 浏览器找到了但起不来：通常是精简服务器缺共享库，
或者装的是 snap / flatpak 包装。

**别在挂机时用同一个账号看直播。** Twitch 的掉宝进度是按账号算的，一边挂一边看会互相干扰。

## 内部结构

只有准备改代码才需要看这段。

```
              +---------------------+        +-----------------------+
              |  twitch.py 引擎     |  调用  |   gui 接口            |
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
              |  + 交互式 shell     |        |  + tk/pystray 控件   |
              +----------+----------+        +----------------------+
                         |
              +----------v----------+
              |  commands.py        |
              |  CommandRegistry    |
              +---------------------+
```

引擎从不直接 import `cli` 或 `commands`，只调 `self.gui.*`。`CLIManager` 把引擎用到的
方法全实现了一遍：`tray.change_icon`、`status.update`、
`channels.set_watching/clear/display`、`progress.display`、`inv.add_campaign`、
`websockets.update`、`login.ask_login`、`login.ask_enter_code`、`set_games`、
`display_drop`、`clear_drop`、`print`、`save`、`start`、`stop`、`close`、
`close_window`、`prevent_close`、`grab_attention`、`coro_unless_closed`、
`wait_until_closed`、`running`、`close_requested`。

新增命令在 `commands.py` 的 `_register_builtins()` 里注册。

## 致谢

这个命令行分支能存在，靠的是别人的工作：

- **[DevilXD/TwitchDropsMiner](https://github.com/DevilXD/TwitchDropsMiner)** ——
  原版程序，以及本分支跑着的整套挂机引擎：GQL 管线、WebSocket 分片、掉宝跟踪、频道切换，
  全部来自上游，MIT 协议。
- **[rangermix/TwitchDropsMiner](https://github.com/rangermix/TwitchDropsMiner)** ——
  浏览器登录助手和 integrity 续签方案。助手协议、Kasada 签发思路、"让它能续签"这个设计
  都出自那个分支，本项目做的是 miner 这一侧。
- Twitch 的掉宝系统，以及上游项目的每一位贡献者。

## 许可证

MIT，和上游一致。原始版权归 [DevilXD](https://github.com/DevilXD)，详见 `LICENSE`。
