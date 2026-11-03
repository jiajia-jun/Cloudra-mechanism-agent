# Cloudra 安装与桌面启动

[English](INSTALL.md) · [返回首页](../README_CN.md)

普通用户下载适合自己系统的安装包，双击安装，再从应用程序或桌面打开 Cloudra。安装包已包含 Python、Node.js、基础依赖和网页界面，无需先安装开发工具。

| 系统 | 安装包 | 安装后从这里打开 |
| --- | --- | --- |
| macOS，Apple Silicon | `Cloudra-<版本>-macos-arm64.pkg` | “应用程序”中的 Cloudra |
| macOS，Intel | `Cloudra-<版本>-macos-x86_64.pkg` | “应用程序”中的 Cloudra |
| Ubuntu / Debian 桌面，x86_64 | `Cloudra-<版本>-linux-x64.deb` | 应用菜单中的 Cloudra |
| 其他兼容 Linux 桌面，x86_64 | `Cloudra-<版本>-linux-x64.tar.gz` | 解压目录中的 Cloudra |
| Windows，原生 x64 | `Cloudra-<版本>-windows-x64-Setup.exe` | 开始菜单或桌面的 Cloudra |

Windows 的详细步骤见 [`windows` 分支教程](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/windows/docs/INSTALL_WINDOWS_CN.md)。需要修改程序或自行部署时，见后面的[从源码安装](#从源码安装)。

## 下载安装包

当前安装包通过 GitHub Actions 的构建产物提供，尚未作为正式版本发布到 Releases。文件是否可下载，以对应打包工作流成功完成并上传产物为准。

1. 登录 GitHub，打开项目的 [Actions 页面](https://github.com/yyywaa/Cloudra-mechanism-agent/actions)。
2. 选择对应系统的打包工作流，打开目标分支最近一次成功的构建。
3. 在页面底部的 **Artifacts** 区域下载对应系统与架构的产物，名称见下表。
4. 解压下载的外层 ZIP，找到其中的 `.pkg`、`.deb`、`.tar.gz` 或 `Setup.exe` 文件。

| 系统 | 打包工作流 | 产物名称 |
| --- | --- | --- |
| macOS | [macOS installer](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/package-macos.yml) | `Cloudra-macos-arm64` 或 `Cloudra-macos-x86_64` |
| Linux | [Linux desktop packages](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/package-linux.yml) | `Cloudra-linux-x64` |
| Windows | [Windows 安装包](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/windows-installer.yml) | `windows-installer-x64` |

下载构建产物需要登录 GitHub，参见 [GitHub 官方说明](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts)。如果没有对应产物，可等待打包成功，或使用[源码安装](#从源码安装)。

## macOS 安装

1. 点苹果菜单 → “关于本机”：显示 Apple M 系列芯片的选择 `arm64`，显示 Intel 处理器的选择 `x86_64`。
2. 双击 `.pkg`，按系统安装窗口中的“继续”“安装”完成安装；系统可能要求输入管理员密码。
3. 打开 Finder → “应用程序”，双击 **Cloudra**。浏览器会自动打开界面；已有桌面目录时，也会添加桌面的 Cloudra 入口。
4. 以后从“应用程序”、桌面或 Dock 打开。退出时，在 Dock 的 Cloudra 图标上右键选择“退出”，或使用应用菜单的“退出 Cloudra”。

当前测试安装包尚未完成 Apple 开发者签名和公证。若系统阻止打开，在确认文件来自本项目对应构建后，进入“系统设置 → 隐私与安全性”，找到该文件的提示，点击“仍要打开（Open Anyway）”，再按提示确认。安装包或应用首次打开都可能触发提示，见 [Apple 官方说明](https://support.apple.com/en-gb/102445)。

## Linux 安装

桌面安装包以 Ubuntu 22.04 及更新版本、Debian 12 及更新版本为目标；其他发行版可尝试便携包。

### Ubuntu / Debian

双击 `.deb`，在系统的软件安装窗口中点击“安装”，按要求输入密码。随后在应用菜单搜索 **Cloudra** 并打开，浏览器会自动打开界面。首次启动会在已有桌面目录中添加入口；若提示不受信任，可右键选择“允许启动”。

如果系统没有关联 `.deb` 的图形安装程序，可在下载目录打开终端执行：

```bash
sudo apt install ./Cloudra-*-linux-x64.deb
```

### Linux 便携包

便携包使用系统的 `xdg-utils` 和 `lsof` 软件包；缺少时通过发行版的软件管理器安装。`.deb` 已自动声明这些系统依赖。

解压 `.tar.gz` 到准备长期保留的文件夹，双击其中名为 **Cloudra** 的可执行文件。首次启动会添加应用菜单入口；已有桌面目录时，也会添加桌面入口。保留解压后的目录，供这些入口继续使用。

停止时，在应用菜单中的 Cloudra 入口上右键，选择 **Stop Cloudra**。

## 第一次使用与更新

1. 在全局设置（Global Settings）中配置主 Agent 与协作 Agent 的模型、接口地址和凭据，也可使用界面提供的账号登录。
2. 创建项目，选择工作目录，放入结构或已有文件，输入任务后开始使用。
3. 需要计算时，再配置本地或远端计算节点，见[配置指南](CONFIGURATION_CN.md)和[部署文档](README.md#部署与配置)。

安装包包含界面和基础运行环境。ORCA、Gaussian、xTB、CREST 等计算软件及其许可证按任务另行准备。模型调用与联网功能仍需相应的网络和账号配置。

关闭浏览器标签页后，Cloudra 服务仍可继续运行；再次点击应用入口可重新打开界面。退出 Cloudra 服务与取消量子化学作业是不同操作。

更新时，退出 Cloudra 后安装同一系统与架构的新安装包。便携包应解压到新的长期目录，再从新目录启动；保留旧目录中的项目文件和自定义数据，确认后再处理旧目录。

启动失败时查看系统提示；macOS 日志位于 `~/Library/Logs/Cloudra/desktop.log`，Linux 日志位于 `~/.local/state/cloudra/desktop.log`。

## 从源码安装

以下步骤面向开发者、需要安装额外 Python 扩展的用户和自行部署的用户。`master` 分支源码运行于 macOS / Linux；原生 Windows 使用 [`windows` 分支](https://github.com/yyywaa/Cloudra-mechanism-agent/tree/windows)。

### 准备环境

需要 **Python ≥ 3.11**、**Node.js ≥ 22.12** 和 npm，建议先使用 Python 3.13 与 Node.js LTS。

macOS：从 [Python 官方下载页](https://www.python.org/downloads/macos/)安装 Python 3.13 的 `.pkg`，然后运行“应用程序 → Python 3.13 → Install Certificates.command”。再从 [Node.js 官网](https://nodejs.org/en/download)安装 macOS LTS `.pkg`，重开终端。

Ubuntu 24.04 及更新版本：

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
```

从 [Node.js 官方下载页](https://nodejs.org/en/download)选择 **LTS → Linux → nvm → npm**，执行页面给出的安装步骤，重开终端。其他 Linux 发行版使用自己的包管理器准备 Python、venv 和 Git。

### 下载、安装和启动

```bash
git clone --branch master https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent
bash install.sh
bash web.sh
```

也可在项目主页点击 **Code → Download ZIP**，解压到长期保留的目录。macOS 在终端输入 `cd `（末尾有空格），把解压目录拖进窗口并按回车，再运行上面最后两条命令；也可双击源码目录中的 `Install.command` 运行安装。

源码安装程序创建 `.venv`、安装 Python 和 JavaScript 依赖、构建网页并创建桌面入口，无需手动激活环境或在安装时填模型配置。通过 `bash web.sh` 启动时，使用期间保留启动终端。

停止源码版全部 Cloudra 服务：

```bash
.venv/bin/python -m cloudra stop
```

通过 Git 更新时，停止 Cloudra 后在源码目录执行 `git pull --ff-only`，再运行 `bash install.sh`。移动源码目录后需要在新位置删除 `.venv` 并重新安装，不能直接复用旧虚拟环境。

需要额外的化学、PDF 或浏览器工具时，在源码目录按需安装：

```bash
.venv/bin/python -m pip install -e '.[chem,pdf,browser]'
.venv/bin/python -m playwright install chromium
```

PyMOL 另行安装。可选包在不同平台上的可用性不同，安装失败时查看具体报错。

| 源码安装问题 | 处理方法 |
| --- | --- |
| 新 Python 已安装，但选中了旧版 | 运行 `CLOUDRA_PYTHON=python3.13 bash install.sh`。 |
| 桌面入口丢失 | 运行 `.venv/bin/python scripts/create_desktop_shortcut.py` 重新生成。 |
| 浏览器未自动打开或提示未授权 | 复制启动终端里 `web UI:` 后的完整链接，包含 `#token=` 部分。 |
