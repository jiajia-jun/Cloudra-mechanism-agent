# Cloudra 安装与启动

[English](INSTALL.md) · [返回首页](../README_CN.md)

大多数用户直接下桌面安装包就行。安装包里已经打包好了 Python、Node.js、基础依赖和网页界面，不用自己配开发环境，装完双击图标就会在浏览器里打开。

| 系统 | 下载哪个包 | 装完在哪打开 |
| --- | --- | --- |
| macOS（Apple Silicon M 系列） | `Cloudra-<版本>-macos-arm64.pkg` | “应用程序”里的 Cloudra |
| macOS（Intel） | `Cloudra-<版本>-macos-x86_64.pkg` | “应用程序”里的 Cloudra |
| Ubuntu / Debian 桌面（x86_64） | `Cloudra-<版本>-linux-x64.deb` | 应用菜单里的 Cloudra |
| 其他 Linux 桌面（x86_64） | `Cloudra-<版本>-linux-x64.tar.gz` | 解压目录里的 `Cloudra` |
| Windows 原生（x64） | `Cloudra-<版本>-windows-x64-Setup.exe` | 开始菜单或桌面上的 Cloudra |

Windows 的详细步骤单独写在 [`windows` 分支教程](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/windows/docs/INSTALL_WINDOWS_CN.md)。如果你要改代码或者自己部署服务器，直接看后面的[从源码安装](#从源码安装)。

## 下载安装包

macOS 和 Linux 的包直接去 [v0.1.1 Release](https://github.com/yyywaa/Cloudra-mechanism-agent/releases/tag/v0.1.1) 下载。Mac 选芯片对应的 `arm64` 或 `x86_64`；Linux x86_64 优先下 `.deb`，非 Debian 系用便携 `.tar.gz`。

实验性的 Windows 安装包由 `windows` 分支构建，登录 GitHub 后在 [Windows installer 工作流](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/windows-installer.yml) 的最近一次成功记录里下载 `windows-installer-x64`。

## macOS 安装

1. 点左上角苹果菜单 → **关于本机**：芯片写 Apple M 系列就下 `arm64`，写 Intel 就下 `x86_64`。
2. 双击 `.pkg`，一路点“继续”“安装”，按提示输入 Mac 密码。
3. 打开 Finder → **应用程序**，双击 **Cloudra**，浏览器会自动弹出来。桌面上也会顺手放一个快捷入口。
4. 平时想彻底退出服务，在 Dock 里的 Cloudra 图标上右键选“退出”，或者点顶部菜单栏的“退出 Cloudra”。

因为现在的测试包还没买苹果开发者公证，第一次打开时 macOS 可能会拦截。安装包旁边附带了 `Unblock-Cloudra.command`，具体用法看[首页的解除拦截说明](../README_CN.md#macos-首次打开被拦截)。也可以手动去“系统设置 → 隐私与安全性”里找到对应提示，确认文件来自本仓库后点“仍要打开（Open Anyway）”，参考 [Apple 官方说明](https://support.apple.com/en-gb/102445)。

## Linux 安装

桌面包主要针对 Ubuntu 22.04+ 和 Debian 12+；其他发行版建议用便携包。

### Ubuntu / Debian

双击 `.deb` 用系统软件中心点“安装”即可，或者在下载目录开终端跑一行：

```bash
sudo apt install ./Cloudra-*-linux-x64.deb
```

装完在应用菜单搜 **Cloudra** 打开。首次启动会在桌面放快捷方式；如果桌面系统提示不受信任，右键选“允许启动”就行。

### Linux 便携包

便携包依赖系统的 `xdg-utils` 和 `lsof`（`.deb` 已经自动声明了，便携包缺的话用系统包管理器装一下）。

把 `.tar.gz` 解压到一个你打算长期放着不动的目录，双击里面的 **Cloudra** 启动。首次启动会自动建好应用菜单和桌面入口，所以别把解压目录删了。想彻底停掉服务时，在应用菜单里的 Cloudra 图标上右键选 **Stop Cloudra**。

## 第一次使用与更新

1. 打开右上角或左下角的 **全局设置（Global Settings）**，填好主 Agent 和协作 Agent 的模型与 API Key，或者直接用内置的 ChatGPT / Codex 账号登录。
2. 新建一个项目，选好工作目录，放进分子结构或已有计算文件，在对话框里交代任务就能开跑。
3. 需要跑量化或分子动力学计算时，再去配本地或远程节点，见[配置指南](CONFIGURATION_CN.md)和[部署文档](README.md#部署与配置)。

有几件事提前心里有数：

- 安装包只含 Cloudra 本体和基础运行环境；ORCA、Gaussian、xTB、CREST 等专业计算软件以及它们各自的许可证需要你按需另装。
- 关掉浏览器标签页不会停掉后台服务，再点桌面图标就能重新连上。彻底退出 Cloudra 和取消正在跑的量化计算也是两回事——已经提交到后台的计算任务不会因为你关网页就死掉。
- 更新版本时，先退出 Cloudra，再直接装新版本安装包覆盖就行。便携包建议解压到新目录启动，确认项目数据都在再删旧目录。
- 万一启动失败，去翻日志定位：macOS 在 `~/Library/Logs/Cloudra/desktop.log`，Linux 在 `~/.local/state/cloudra/desktop.log`。

## 从源码安装

想改代码、装额外 Python 扩展，或者在无图形界面的服务器上跑，用源码方式最省心。`master` 分支面向 macOS 和 Linux；原生 Windows 切到 [`windows` 分支](https://github.com/yyywaa/Cloudra-mechanism-agent/tree/windows)。

### 准备环境

需要 **Python ≥ 3.11**、**Node.js ≥ 22.12** 和 npm（推荐 Python 3.13 + Node.js LTS）。

macOS 可以直接去 [Python 官网](https://www.python.org/downloads/macos/) 装 3.13 的 `.pkg`（装完顺手双击“应用程序 → Python 3.13 → Install Certificates.command”），再去 [Node.js 官网](https://nodejs.org/en/download) 装 macOS LTS `.pkg`，装完重开终端。

Ubuntu 24.04+ 先装基础包：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
```

然后按 [Node.js 官网](https://nodejs.org/en/download) 的 **LTS → Linux → nvm → npm** 步骤装好 Node.js 并重开终端。

### 下载、安装和启动

```bash
git clone --branch master https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent
bash install.sh
bash web.sh
```

不想用 Git 也可以在仓库首页点 **Code → Download ZIP** 解压，macOS 里甚至可以直接双击目录里的 `Install.command`。`install.sh` 会自动建 `.venv`、装好前后端依赖、编完网页并建好桌面图标。用 `bash web.sh` 启动期间别关那个终端窗口。

要停掉源码版全部服务：

```bash
.venv/bin/python -m cloudra stop
```

以后更新源码时，先停服务，再在仓库目录里跑：

```bash
git pull --ff-only
bash install.sh
```

注意如果你把整个源码文件夹挪了地方，旧的 `.venv` 路径会失效，删掉 `.venv` 重新跑一遍 `bash install.sh` 就好。

需要额外的化学、PDF 解析或浏览器抓取扩展时按需装：

```bash
.venv/bin/python -m pip install -e '.[chem,pdf,browser]'
.venv/bin/python -m playwright install chromium
```

PyMOL 需要单独安装。

### 常见小坑

| 遇到什么问题 | 怎么修 |
| --- | --- |
| 装了新 Python 但脚本还是捡到旧版 | 用 `CLOUDRA_PYTHON=python3.13 bash install.sh` 指定解释器。 |
| 桌面快捷方式不见了 | 跑 `.venv/bin/python scripts/create_desktop_shortcut.py` 重建。 |
| 浏览器没自己打开，或者打开报未授权 | 复制终端里 `web UI:` 后面那一整串带 `#token=` 的链接粘进地址栏。 |
