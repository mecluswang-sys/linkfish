# WoW 钓鱼助手 macOS 版（前台模式）

这是**独立于 Windows 版的一份实现**。项目根目录的 `program.py` 保持原样，只在 Windows 上运行；
本目录的 `wow_fishing_mac.py` 只在 macOS 上运行，依赖和虚拟环境也完全分开，互不影响。

| | Windows 版 | macOS 版 |
|---|---|---|
| 入口 | `../program.py` | `wow_fishing_mac.py` |
| 依赖 | `pywin32` 等 | `pyobjc` 系列 |
| 按键方式 | `PostMessage` 后台投递 | `CGEvent` 前台注入 |
| 运行要求 | 游戏可在后台 | **游戏必须在前台** |

## 方案说明：为什么是前台模式

macOS 没有 Windows 的 `HWND` 和 `WM_KEYDOWN` 消息机制，无法稳定地向后台窗口投递按键。
因此本版本采用前台模式：游戏窗口处于最前面时才发送按键。

程序会自动处理焦点变化：

- 切换到其他应用 → **自动暂停**，不再发送任何按键
- 切回游戏 → **自动恢复**并重新抛竿
- 游戏退出 → 自动停止

界面默认开启「窗口置顶」，这样助手面板会浮在游戏上方，但键盘焦点仍在游戏里。

界面上的「注入方式」还提供了一个 `指定进程（实验）` 选项，使用 `CGEventPostToPid`
直接向游戏进程投递事件，理论上不要求前台。**这是实验性功能，是否生效取决于游戏客户端，
不保证可用**，默认请使用 `HID 层（推荐）`。

## 环境准备

需要 macOS 11 及以上、Python 3.9+。**请单独建立虚拟环境，不要和 Windows 环境混用。**

```bash
cd macos
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## 授权设置

首次运行必须授予两项权限，否则按键或音频会静默失败。

### 1. 辅助功能（必需，用于发送按键）

`系统设置 → 隐私与安全性 → 辅助功能`，添加并勾选运行本程序的宿主：

- 直接用命令行运行时，添加的是**终端 App**（Terminal 或 iTerm）
- 打包成 `.app` 后，添加的是 `WoWFishingMac.app`

修改权限后需要**完全退出并重启**该程序，权限才会生效。

### 2. 麦克风（必需，用于监听咬钩声）

`系统设置 → 隐私与安全性 → 麦克风`，允许对应程序。程序启动时会主动请求一次。

## 音频采集：用 BlackHole 替代 VB-Cable

项目根目录的 `VB-Cable.zip` 是 Windows 驱动，**在 Mac 上不能用**。
macOS 需要改用虚拟音频设备来捕获游戏声音：

```bash
brew install blackhole-2ch
```

然后在「音频 MIDI 设置」中创建一个**多输出设备**，同时勾选 `BlackHole 2ch` 和你的扬声器/耳机，
把系统输出设为该多输出设备。这样你能照常听到声音，程序也能从 `BlackHole 2ch` 读到游戏音频。

最后在程序的「音源输入设备」里选择 `BlackHole 2ch`。

> 注意：macOS 的默认采样率通常是 48000 而不是 44100。程序会自动尝试回退，无需手动设置。

## 运行

```bash
source .venv/bin/activate
python wow_fishing_mac.py
```

使用步骤：

1. 选择游戏应用（通常会自动识别 World of Warcraft）
2. 选择音源输入设备（BlackHole 2ch）
3. 调整判定阈值，观察右侧波形确认咬钩时能超过红线
4. 配置抛竿键、起竿键
5. 需要时添加定时按键（补 Buff、鱼饵等）
6. 点击「开启自动钓鱼」，程序会自动把游戏切到前台，5 秒后开始

## 打包为 .app

必须在 Mac 上执行：

```bash
source .venv/bin/activate
pip install pyinstaller
pyinstaller WoWFishing-macOS.spec
```

产物在 `dist/WoWFishingMac.app`。

打包后需要重新在「辅助功能」里授权这个 `.app`。如果每次重新打包权限都失效，
可以做一次 ad-hoc 签名让标识保持稳定：

```bash
codesign --force --deep --sign - dist/WoWFishingMac.app
```

## 与 Windows 版的功能差异

- **没有后台运行**：这是 macOS 的系统限制，不是实现问题
- **没有窗口句柄**：改为选择应用进程，不再有「把窗口压到底层」的操作
- **按键支持范围**：支持字母、数字、常见符号，以及 `f1`~`f12`、`space`、`tab`、`esc`、`num0`~`num9`
  等名称；不支持需要组合键输入的字符
- 新增「暂停/恢复」和「窗口置顶」，用于配合前台模式

## 免责声明

本项目仅作学习、研究和备份开发参考。使用前请遵守当地游戏规则、平台规定以及相关法律法规。
自动化操作可能违反游戏使用条款并被反作弊机制识别，风险自负。
