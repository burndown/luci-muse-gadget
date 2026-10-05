# 用蓝牙给路由器配对 Muse

Muse 的 Linux 客户端只在第一次配对时用到蓝牙。配对时手机通过 BLE 把设备令牌交给设备，之后设备就靠网络直连 Muse，蓝牙再也不需要了。OpenWrt 上没有 SDK 配对所需的 `python3-dbus` 和 `python3-gi`，路由器本身也往往没有蓝牙芯片，所以最省事的办法是借一台带蓝牙的 Linux 机器配对一次，把结果打包成一行文字，粘贴到路由器的 LuCI 页面里。

## 你需要准备

一台带蓝牙 4.0 以上（BLE）的 Debian、Ubuntu 或树莓派系统的机器，笔记本、树莓派、迷你主机都行，没有蓝牙的话插一个 USB 蓝牙适配器。macOS 和 Windows 不行，因为 SDK 的配对部分依赖 Linux 的 BlueZ。虚拟机也可以，只要把蓝牙适配器直通进去。

还需要一个 SDK token。到 gadgets.muse.ai 登录，在 Account 的 SDK tokens 里生成，格式是 `mgst_` 开头的一串字符。使用前请先读一下官方的 Gadget SDK Terms。手机上要装 Muse App。

## 第一步：在路由器上安装

把本项目目录拷到路由器上执行安装脚本：

```sh
scp -O -r luci-muse-gadget root@路由器地址:/tmp/
ssh root@路由器地址 'sh /tmp/luci-muse-gadget/install.sh'
```

装完以后，LuCI 的“服务”菜单里会出现“Muse Gadget”。这时先别启用，等配对完再开。

## 第二步：在带蓝牙的 Linux 机器上配对

把 `tools/pair-on-linux.sh` 拷到那台机器上运行：

```sh
bash pair-on-linux.sh
```

脚本会让你输入 SDK token（输入时不会回显），自动安装 BlueZ 等依赖，下载 SDK，然后打开一个 10 分钟的配对窗口，并显示设备的蓝牙名，形如 `MuseGadgetB19C5C`。

这时拿起手机，打开 Muse App，进入“设置 → 设备”，先打开 Developer mode，再点右上角的 **+** 添加设备，选择刚才显示的那个名字。App 会警告这是社区设备，确认继续即可。接下来 App 可能让你选 Wi-Fi，选当前网络就行。

配对成功后，脚本会打印一行以 `MUSE1:` 开头的长文本，这就是配对包。把整行复制下来。脚本结束时会清掉临时目录里的令牌，并询问要不要卸载它刚装的软件包。

## 第三步：把配对包导入路由器

在 LuCI 的“服务 → Muse Gadget”页面，把配对包粘贴到“Pairing”下面的文本框里，点“Import pairing bundle”。然后勾选“Enable”，保存并应用。状态栏里“Service”变成 Running、“Paired with Muse”变成 Yes，就说明已经连上了。日志里出现 `registered with the Muse` 是最直接的证据。

## 常见问题

**手机里搜不到设备。** 最常见的原因是设备已经被另一个蓝牙工具连着了。BLE 设备被某个主机连接时会停止广播，所以如果你用过 nRF Connect 之类的工具去测试连接，请先断开并关闭那个 App。其次确认 Developer mode 已打开、手机蓝牙权限已给 Muse、手机离那台 Linux 机器近一些。配对窗口只有 10 分钟，过期后重新运行脚本就行。

**App 提示连接 Wi-Fi 失败。** 这是无害的。设备本来就在线，SDK 会忽略 App 发来的 Wi-Fi 凭证，实际配对已经完成。以脚本打印出配对包为准。

**已经连着一个 ESP32 设备。** 官方文档没有说明同时能不能挂多个开发者设备，我也没有验证。如果配对时 App 找不到新设备，可以先把 ESP32 暂时断开再试。

**同一个配对包不要在两个地方同时运行。** 它代表同一个设备身份。导入路由器之后，不要在原来的 Linux 机器上再启动 SDK 服务。

**配对包的安全。** 它里面有设备令牌和你的 SDK token，等同于密码，不要发到聊天群或贴到公开的地方。如果泄露了，在 gadgets.muse.ai 吊销 SDK token，并在 LuCI 里点 Unpair 重新配对。

## 想直接在路由器上配对？

理论上可以，前提是路由器有 USB 蓝牙适配器，并且装上 `kmod-bluetooth`、`kmod-btusb`、`bluez-daemon`。但 SDK 的配对部分还需要 `python3-dbus` 和 `python3-gi`，这两个包目前在官方 OpenWrt 仓库里没有，要自己编译，所以不推荐。借一台 Linux 机器配对一次，是最稳妥的办法。
