# luci-muse-gadget

在 OpenWrt / ImmortalWrt 路由器上运行 Meta 的 [Muse Gadget SDK](https://github.com/facebookincubator/muse-gadget-sdk) Linux 客户端，并提供 LuCI 管理页面（服务 → Muse Gadget）。装好之后，你的路由器会作为一个 Muse gadget 出现在 Muse App 里，Muse 可以查看路由器状态、局域网设备、流量和日志，在你允许的前提下还能重启服务或路由器。

官方 SDK 面向树莓派和 Debian：安装脚本依赖 apt 和 systemd，配对依赖蓝牙。本项目解决三件事：让它能在 OpenWrt 的 procd 和 musl 环境下跑；把唯一需要蓝牙的配对步骤拆出来，借一台带蓝牙的 Linux 机器做一次就行；把路由器能提供的能力做成可勾选的命令，而不是只给 Muse 一个低权限 shell。

这是社区项目，和 Meta 没有关联，也没有得到 Meta 的认可。SDK 本身是 Meta 的 Apache-2.0 项目，本仓库不包含 SDK 源码，安装时从 Meta 官方仓库下载。使用时须遵守其 [Gadget SDK Terms](https://gadgets.muse.ai/sdk-terms)：SDK token 仅限个人、非商业使用，不能与他人共享，也不能用来访问别人的 Muse 账号。每个使用者请生成自己的 token。

## 开始之前

你需要一台运行 OpenWrt 或 ImmortalWrt 的路由器，能用 SSH 登录，能访问外网（要下载软件包和 Muse 的服务），并且装了 LuCI。我在 ImmortalWrt 25.12.1 x86_64 上测试过，用的是 apk 包管理器，旧版 OpenWrt 的 opkg 分支我没有测过。因为全部是纯 Python，其他架构预期也能跑，但没有验证。Python 3 及其依赖大约占用 30MB（我这边 Python 标准库 27MB，加上本项目 2MB），另外还有 cryptography 等包，请预留 50MB 以上的空间。

你还需要一个 SDK token：登录 [gadgets.muse.ai](https://gadgets.muse.ai/settings/sdk-tokens)，在 Account → SDK tokens 里生成，格式是 `mgst_` 开头的一串字符。每个 gadget 配对都需要它。手机上要装 Muse App。

另外要有一台带蓝牙（BLE）的 Debian、Ubuntu 或树莓派系统的 Linux 机器，只在配对那几分钟用到。macOS 和 Windows 不行。没有的话，可以买一个几十块的 USB 蓝牙适配器插到任意 Linux 机器或虚拟机上。

## 第一步：在路由器上安装

把项目下载到你的电脑，再拷到路由器上执行安装脚本：

```sh
git clone https://github.com/burndown/luci-muse-gadget.git
scp -O -r luci-muse-gadget root@路由器地址:/tmp/
ssh root@路由器地址 'sh /tmp/luci-muse-gadget/install.sh'
```

脚本会安装 `python3`、`python3-cryptography`、`python3-pip`、`bash`、`shadow-useradd` 和 `curl`，下载固定版本的官方 SDK，用 pip 安装 SDK 要求的 websockets 15（路由器软件源里的版本太旧），然后装上服务脚本和 LuCI 页面。看到 `Done.` 就说明装好了。刷新 LuCI，“服务”菜单里会出现 “Muse Gadget”。

如果路由器访问不了 GitHub，可以先在电脑上 clone 官方 SDK，再用 `SDK_DIR=/tmp/muse-sdk sh install.sh` 指定本地副本。PyPI 访问不了的话设置 `PIP_INDEX_URL` 指向镜像。

安装到这里还不会连接 Muse，因为还没有配对。

## 第二步：配对（需要蓝牙，只做一次）

配对时手机通过蓝牙把设备令牌交给设备，之后设备靠网络直连 Muse，蓝牙不再需要。这一步在带蓝牙的 Linux 机器上做，完成后会得到一行配对包，下一步导入路由器。

把 [tools/pair-on-linux.sh](tools/pair-on-linux.sh) 拷到那台机器上运行：

```sh
bash pair-on-linux.sh
```

脚本会让你输入 SDK token（不会回显），安装 BlueZ 等依赖，下载 SDK，然后打开一个 10 分钟的配对窗口，并显示设备的蓝牙名，形如 `MuseGadgetB19C5C`。这时拿起手机：

1. 打开 Muse App，进入 设置 → 设备，打开 **Developer mode**。
2. 点右上角的 **+** 添加设备，选择刚才显示的 `MuseGadget…`。
3. App 提示这是社区设备时，确认继续。
4. 如果让你选 Wi-Fi，选当前网络即可。即使最后 App 提示“连接 Wi-Fi 失败”也不用在意，设备本来就在线，SDK 会忽略 Wi-Fi 凭证，以脚本打印出配对包为准。

成功后脚本会打印一行以 `MUSE1:` 开头的长文本，复制下来。脚本结束时会清理临时目录里的令牌，并问你要不要卸载它装的软件包。更详细的步骤和排错见 [docs/pairing.md](docs/pairing.md)。

## 第三步：导入配对包并启用

打开 LuCI → 服务 → Muse Gadget。在 Pairing 区块把配对包粘进文本框，点 **Import pairing bundle**。然后在“设置”里勾选 **Enable**，点“保存并应用”。

几秒钟后，页面顶部的状态应该是：Service 运行中、依赖确认、Paired with Muse 是、SDK token Saved。页面下方的日志里出现 `registered with the Muse`，就说明已经连上了。这时 Muse App 的设备列表里会看到它在线。

## 第四步：选择向 Muse 开放什么

默认情况下，Muse 只拿到 SDK 的四个通用命令：以 `muse` 账号运行的任意 shell 命令、文件读写、设备健康。这个账号权限很低，在路由器上几乎看不到什么。要让 Muse 真正能帮你看路由器，在“Capabilities offered to Muse”里勾选需要的能力，保存并应用，服务会重启并把新的命令列表重新注册给 Muse：

| 命令 | 类型 | 作用 |
|---|---|---|
| `router.status` | 只读 | 型号、固件、运行时间、负载、内存、连接数、各接口状态与地址 |
| `router.clients` | 只读 | 局域网设备的 IP、MAC、主机名（DHCP 租约加 ARP） |
| `router.traffic` | 只读 | 各接口累计流量，可选采样得到实时速率 |
| `router.services` | 只读 | 服务列表，是否开机自启、是否在运行 |
| `router.log` | 只读 | 系统日志最近若干行，可按关键字过滤 |
| `router.ping`、`router.dns_lookup` | 只读 | 从路由器发起连通性和 DNS 测试 |
| `router.service_control` | 会改动路由器 | 启动、停止、重启你在白名单里列出的服务，不能操作 musegadget 自己 |
| `router.reboot` | 会改动路由器 | 重启路由器，必须带 `confirm=true` |

这些命令以 root 在服务进程里执行，但只跑固定的参数列表，不经过 shell，每个参数都经过校验。如果你想让 Muse 只能用这些具名命令，可以关掉“Allow a shell”和“Allow file access”。选 `router.service_control` 时，要在“Services Muse may control”里填写允许它操作的服务名，比如 `dropbear`。

注意：只读不等于没有隐私影响。`router.clients` 会把你局域网里设备的名字和 MAC 地址交给 Muse，`router.log` 也可能包含敏感信息。只勾你需要的。

## 第五步：验证

在 Muse 里直接问，比如“我的路由器现在负载怎么样”“局域网里有哪些设备在线”“从路由器 ping 一下 1.1.1.1”。路由器上看日志能确认命令被调用：

```sh
logread -e musegadget | tail
```

每次调用会出现 `invoke router.status` 之类的记录，以及结果状态（不会记录参数和输出）。

## 常见问题

**Service 显示 Stopped。** 先看有没有导入配对包并勾选 Enable。服务只在“已启用且已配对”时启动，否则日志里会有 `not paired yet`。其他原因看 LuCI 页面下方的日志，或者 `logread -e musegadget`。

**手机里搜不到设备。** 最常见的原因是设备已经被另一个蓝牙工具连着了，BLE 设备被连接时会停止广播。关掉 nRF Connect 之类的 App，确认 Developer mode 已打开，手机离配对机器近一点，重新运行脚本。详见 [docs/pairing.md](docs/pairing.md)。

**我还有一个 ESP32 的 Muse 设备。** 同一个 Muse 下能不能同时挂多个设备，我没有验证。我的 ESP32 在配对期间是断开的。如果找不到新设备，可以先把它暂时断开。

**同一个配对包不要在两个地方同时运行。** 它代表同一个设备身份。导入路由器后，不要在配对用的 Linux 机器上再启动 SDK。

**重启路由器后会自动重连吗。** 会。我在 ImmortalWrt 上实际重启过，开机约 40 秒内服务自动启动并重新注册到 Muse。如果你那边没连上，请看日志并反馈。

**升级。** 拉取新版本后重新执行 `install.sh`，配对和设置会保留。

**卸载。** `sh install.sh --uninstall` 删除程序但保留 `/etc/musegadget`（配对数据），加 `--purge` 一并删除。

## 权限与安全

Muse 能在你的设备上执行命令，所以这一节请读完再决定开放什么。

### 谁以什么身份运行

服务由 procd 以 root 启动，只负责连接 Muse 和调度。Muse 发来的通用命令（`system.run`、`file.read`、`file.write`）会被**降权**到 `muse` 账号再执行：SDK 为每条命令的子进程设置该账号的 uid、gid 和附加组，并把环境变量重置为固定的 PATH 和 HOME。`run_as` 为空或设为 `root` 时，服务拒绝启动，不会退回 root。

OpenWrt 上没有 `adduser`、`su` 和 `sudo`，所以启动脚本用 `shadow-useradd` 提供的 `useradd -M -s /bin/bash muse` 自动创建这个账号。它没有设密码，没有附加组，不能直接登录。SDK 的 `system.run` 固定调用 `/bin/bash -c`，而 OpenWrt 默认只有 busybox ash，所以安装脚本会装 `bash`。

配对令牌和 SDK token 存放在 `/etc/musegadget`，目录权限 700、属主 root，`muse` 账号读不了，Muse 也就拿不到自己的凭证。本地 socket `/var/run/musegadget.sock` 属主 root、属组 `muse`、权限 660，只有 `muse` 账号下的程序才能用它给 Muse 发消息。

### `muse` 账号在 OpenWrt 上实际能做什么

下面是在 ImmortalWrt 25.12.1 上，用 `muse` 的 uid 实际执行得到的结果，不同系统和已装插件可能不一样：

| | 结果 |
|---|---|
| 读 `/etc/shadow` | 拒绝 |
| 读 `/etc/config/` 里的 `network`、`dhcp`、`dropbear`、`rpcd`、`samba4`、`ddns-go` | 拒绝（这些文件权限是 600） |
| 读 `/etc/musegadget`（令牌目录） | 拒绝 |
| 在 `/etc` 下写文件 | 拒绝 |
| 调用 ubus | 只能看到 `dnsmasq.dns`，`system board`、`network.interface dump` 都找不到，也读不到 `logread` |
| 在 `/tmp`、`/home/muse` 下读写 | 允许 |
| `ip neigh` 查看邻居、对局域网主机建立 TCP 连接 | 允许 |
| 读全员可读（644）的文件 | 允许 |

没有实测的有两项：让 `muse` 执行 `reboot` 或 `/etc/init.d/xxx restart`。这两个万一没挡住会直接断网，所以没有试。根据 ubus 访问受限和 `/etc` 不可写来推断它做不到，但这只是推断。

**要特别注意**：路由器上凡是全员可读的文件，`muse` 的 shell 都读得到。我的测试机上，`/etc/config/firewall`、`/etc/config/openclash` 以及 OpenClash 的订阅配置目录里的文件都是 644，这类配置通常含有代理节点地址和凭证。这是系统和那些插件自己的权限设置，不是本项目造成的，但开着通用 shell 时它就成了暴露面。你可以用 `ls -l /etc/config` 检查，对不需要公开的文件执行 `chmod 600`，或者直接关掉通用 shell。另外，`muse` 账号能访问整个局域网，等于给了 Muse 一个局域网内的跳板。

### 具名命令的权限模型

`router.*` 具名命令不经过降权，**在服务进程里以 root 执行**，因为它们要读 ubus、系统日志，要重启服务。所以它们的安全靠另外几道约束：每个命令只执行写死的参数列表，不经过 shell；所有外部参数都经过校验，主机名和服务名用严格的正则，数字限定范围；`router.service_control` 只能操作你在白名单里填写的服务，并且硬性禁止操作 musegadget 自己；`router.reboot` 必须带 `confirm=true`；没有勾选的命令既不会注册给 Muse，被调用时也会拒绝。

这里有一个取舍：具名命令的权限比通用 shell 更高（root），换来的是可控，它能做的事是固定的，且是你勾选的。你可以只勾只读项，再关掉“Allow a shell”和“Allow file access”，这样 Muse 能做的事比默认配置更少。

### 建议的配置

| 你的需求 | 建议 |
|---|---|
| 想试试，不太放心 | 只勾 `router.status`、`router.ping`、`router.dns_lookup`，关掉通用 shell 和文件读写 |
| 想让 Muse 帮你看家里网络 | 再勾 `router.clients`、`router.traffic`、`router.log`，同样关掉通用 shell |
| 想让 Muse 能处理故障 | 再开 `router.service_control`，白名单里只填需要它重启的服务，不要填 `network`、`firewall`、`dropbear` 这类关键服务 |
| 想让 Muse 能重启路由器 | 开 `router.reboot`，务必想清楚，并确认你能在它重启后找到办法恢复 |

### 数据去向

只读不等于没有隐私影响。命令的返回结果会发给 Muse 的云端：`router.clients` 会带上局域网设备的名字和 MAC 地址，`router.log` 可能包含主机名、IP 和账号相关的日志，`router.status` 会带上你的接口地址。只勾你需要的。

### 令牌与泄露处理

配对包和 SDK token 等同于密码：不要发到聊天群或公开的地方。SDK token 按官方条款仅限个人使用，不能共享。一旦泄露，在 gadgets.muse.ai 吊销 SDK token，在 LuCI 里点 Unpair，再重新配对。

## 它是怎么工作的

读 SDK 源码得到的结论是：日常运行（`musegadget run`）完全不碰蓝牙，只需要 Python 3、`cryptography` 和 `websockets>=13`，通过 Noise 加密会话连 Muse；蓝牙只在 `musegadget pair` 里用一次，通过 BlueZ 的 D-Bus 接口。所以配对和运行可以分开在两台机器上。

具名命令由 `musegadget_router` 包装层实现：它在 SDK 启动前把启用的命令加进 SDK 向 Muse 注册的命令表，并在 SDK 自己的命令处理之前响应它们，SDK 源码不需要修改。

```
install.sh                                      在路由器上安装 / 卸载
tools/pair-on-linux.sh                          在带蓝牙的 Debian 系机器上配对，输出 MUSE1:... 配对包
docs/pairing.md                                 配对详细教程与排错
files/etc/config/musegadget                     UCI 配置
files/etc/init.d/musegadget                     procd 服务
files/usr/libexec/rpcd/musegadget               rpcd 后端：状态、日志、导入配对包等
files/usr/lib/musegadget/musegadget_router/     具名命令（包装 SDK）
files/usr/share/{rpcd/acl.d,luci/menu.d}/       LuCI 权限和菜单
files/www/luci-static/resources/view/musegadget/main.js   LuCI 页面
```

安装位置：代码在 `/usr/lib/musegadget`，状态（身份、配对令牌、SDK token）在 `/etc/musegadget`，目录权限 700。

## 验证情况

在一台 ImmortalWrt 25.12.1 x86_64（PVE 虚拟机）上验证过：完整配对流程（用另一台 Debian 机器的 Intel AX210 蓝牙）走通；服务连上 Muse 并注册成功，Muse App 里设备显示在线，Muse 实际调用过 `system.run`；LuCI 页面打开正常，状态实时显示，“重启”按钮生效，能勾选能力；路由器重启后服务自动启动并重新注册成功；以 `muse` 的 uid 实测了它的权限边界（见上面的“权限与安全”）；每个具名命令的处理函数都在路由器上直接调用测过，参数注入被拒绝，服务重启后日志确认已广播这些命令。

没有验证的：`muse` 账号执行 `reboot` 和 `/etc/init.d` 重启服务（怕断网，没试）；Muse 实际调用具名命令（本项目写完后）；页面里的导入配对包、保存 token、停止、解除配对按钮没有点过（后端层面测过）；`router.service_control` 的成功路径和 `router.reboot` 没有实际执行；`install.sh` 没有在干净系统上完整跑过，opkg 分支没测；非 x86 架构没测。

没有做成 `.ipk` / `.apk` 软件包，目前通过安装脚本分发。

## 许可

本项目以 Apache License 2.0 发布，见 [LICENSE](LICENSE)。Muse Gadget SDK 是 Meta 的项目，同样采用 Apache-2.0，并另有 Gadget SDK Terms 约束 SDK token 的使用。
