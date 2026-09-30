# 入门指南

从装好到跑起来全程不需要桌面环境 —— 唯一想要块屏幕的是登录那一步，没有屏幕时用
`Xvfb` 顶替。

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
| 系统 | Linux / macOS / Windows，**不需要显示器**；但登录会起浏览器，无屏幕的机器还需要 `Xvfb` |
| 网络 | 能出站访问 `twitch.tv`、`gql.twitch.tv`、`spade.twitch.tv` 的 HTTPS |
| 浏览器 | 需要一个 Chromium 系浏览器：登录和自动续签都要用，见[拿回完整活动列表](#拿回完整活动列表) |

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

### Linux 一条命令

把脚本下载下来跑一遍就行：

```bash
wget -O install_linux.sh https://raw.githubusercontent.com/LCBRST/TwitchDropsMiner-CLI/main/install_linux.sh
chmod +x install_linux.sh
./install_linux.sh
```

它会装好程序需要的系统组件（一个 Chromium 系浏览器，以及无屏幕机器上的 `Xvfb`）、
拉取源码、在你执行脚本的目录里构建出一个自带一切的二进制，**然后把源码和构建环境
一起删掉**。最后剩下的只有浏览器、`Xvfb` 和那个二进制。

```
./install_linux.sh --dry-run     # 只打印要做什么，什么都不改
./install_linux.sh --dir ~/tdm   # 装到别处
./install_linux.sh --keep-source # 保留源码和 venv
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

没有已保存的登录信息时，程序会**打开一个浏览器等你登录**。只有这种会话能看到完整活动
列表，所以值得登的就是它 —— 窗口出现在哪里、以及没有屏幕的机器怎么办，见下面
[拿回完整活动列表](#拿回完整活动列表)。

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

解决办法是**用 miner 自己起的浏览器登录**。那是一个真浏览器，跑在 miner 本机上、用 miner
自己的地址，所以它拿到的会话正是 miner 能继续用的那个。全程没有任何东西被传来传去，
也不需要装第二个程序。

首次运行、以及活动列表再次变少时，程序会主动提出这件事。想自己发起：

```
login browser
```

### 有显示器的机器

浏览器窗口会**直接开在 miner 上**，就这么简单：

```
a browser window has opened on this machine - sign in to Twitch there
```

在那个窗口里登录即可，两步验证、邮箱验证码都正常走。会话到手后窗口会自己关掉。

### 没有显示器的机器

这时 miner 会打印地址，每个可达的地址一行：

```
sign in at http://192.0.2.10:8090/login/xxxxxxxx
on this machine: http://127.0.0.1:8090/login/xxxxxxxx
```

从任何地方（笔记本、手机）打开其中一个。你看到的**不是你自己浏览器里的 Twitch 副本**，
而是 miner 上那个浏览器的**实时画面**，你的鼠标键盘会传回去。点进画面里，就当自己坐在那台
机器前操作。粘贴也好用 —— 密码管理器就是这么把密码送进去的。

无头的 Linux 机器上，miner 会起 `Xvfb` 当浏览器的屏幕。**没装 `Xvfb` 时它会直说**，
而不是给你一个打不开的地址：

```
sudo apt install xvfb      # Debian/Ubuntu；其它发行版用对应的包管理器
```

**上面的 `192.0.2.x` 只是示例**，用你自己 miner 打印出来的那个 —— `192.0.2.0/24` 是保留的
文档网段，永远不会是你的机器。

要从别的机器连，记得在防火墙放行那个端口。

### 确认一下

```
login status
```

应该显示 `imported session: active`，活动数量跳到完整目录。**立刻生效，不用重启。**

之后那个页面会**自己关掉**：它是一个入口，不是控制台，会话进来之后就没有用处了 ——
续签读的是已存的会话。以后再想登录，重新 `login browser`。

### 为什么可能不成功

能不能过，只取决于 Twitch 自己。而它唯一给的把手是"一致性"：如果登录的机器、时钟、时区
和账号平时登录的地方对不上，它会格外挑剔。被拒的话，先把机器时区设对再试。

`login device` 是旧的不需要浏览器的登录方式，给完全没有浏览器的机器用。它认证的客户端
**看不到活动列表**，所以它只能继续挂已经在进行中的掉宝，不能发现新活动。

## 让登录保持有效

导入的会话里带一份 integrity 证明，**寿命由 Twitch 决定，而且给得不长** —— 实测匿名请求给
16 小时，已登录的会话只给 1 小时。miner 会自动续：到期前几分钟，
它临时起一个**无头 Chromium**，把捕获到的会话重放进去，让页面自己重新签一份证明，
验证通过之后才拿它替换旧的。

**前提是跑 miner 的机器上得有一个 Chromium 系浏览器**（和登录用的是同一个），
除此之外对机器没有别的要求 —— 不用显示器，也不用桌面环境。（完全没有浏览器的机器
仍然可以用 `login device` 跑，只是能看到的活动少。）

- 查找顺序：`PATH` 里的 `chromium` / `chrome`，然后是各平台的默认安装位置（Windows 上还会找 Edge）。
- 想指定具体某个：

  ```
  set renewal_browser_path C:\Program Files\Google\Chrome\Application\chrome.exe
  set renewal_browser_path /usr/bin/google-chrome      # Linux 和 macOS
  ```

- `login status` 会显示续签状态：`renewal: automatic, using ...`，或者 `renewal: unavailable - <原因>`。

不用等到期，可以手动触发一次：

```
login renew
```

续签一直失败也不会把程序搞坏：它会退避重试，期间照常使用当前会话；等会话真过期了，
自动退回 `cookies.jar`。那时候 `login browser` 重新登一次即可。

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
然后 `login status` 里的续签状态应该变成 `renewal: automatic, using …`。

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
| 看登录状态 | `whoami`、`login status` |

## 命令一览

`help` 会列出全部，这里是完整的一份。

**通用** —— `help [命令]`、`status`、`version`、`log [N]`、`clear`、
`exit` / `quit` / `q`

**登录** —— `whoami`、`login [browser|status|cancel|renew|device]`

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
| `imported-session.json` | 从登录浏览器里捕获的会话 —— **同样是凭据** |
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

**登录页一直不出现画面。** miner 上那个浏览器没起来。看 `login status`，以及日志里的
`The browser sign-in did not complete (<码>)`：

| 码 | |
|---|---|
| `BROWSER_MISSING` | 机器上没有 Chromium 系浏览器 —— 见 [Linux 上怎么装浏览器](#linux-上怎么装浏览器) |
| `BROWSER_DISPLAY` | 没有显示器，也没有 `Xvfb` 顶替 |
| `BROWSER_START` | 浏览器找到了但起不来：通常是缺共享库，或者装的是 snap / flatpak 包装 |
| `BROWSER_PROTOCOL` | 浏览器不再响应 |
| `ACCOUNT_MISMATCH` | 这次登录的账号和 miner 当前用的不是同一个 |

**登录被拒。** Twitch 拒了它 —— 见[为什么可能不成功](#为什么可能不成功)。日志里的
`Twitch did not accept a captured login context (<码>)` 会指出卡在哪一步。

**什么都没发生，也没打印地址。** 说明这台机器有显示器，miner 直接在那里开了窗口 ——
去桌面上找。想从别处登录的话，`login status` 任何时候都会显示地址。

**续签显示不可用。** 看 `login status` 里的原因。最常见的是没找到 Chromium 系浏览器
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
  integrity 续签方案：把捕获到的会话重放进无头浏览器、让 Kasada 自己的脚本签下一份新证明。
  本项目的续签就是这套。浏览器登录则是在那个 fork 退役它的桌面助手之后，从同一个思路
  长出来的 —— 当初的助手协议、Kasada 签发思路、"让它能续签"这个设计都出自那个分支，
  本项目做的是 miner 这一侧。
- Twitch 的掉宝系统，以及上游项目的每一位贡献者。

## 许可证

MIT，和上游一致。原始版权归 [DevilXD](https://github.com/DevilXD)，详见 `LICENSE`。
