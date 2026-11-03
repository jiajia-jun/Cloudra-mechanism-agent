# Cloudra 安装与桌面启动

[English](INSTALL.md) · [返回首页](../README_CN.md)

安装完成后，双击桌面入口即可启动 Cloudra，并在浏览器中打开界面。首次安装需要联网下载依赖；模型账号在界面里配置。

| 你的系统 | 从这里开始 |
| --- | --- |
| macOS，Apple Silicon 或 Intel | [macOS 安装](#macos-安装) |
| Linux，下面以 Ubuntu 24.04 及更新版本为例 | [Linux 安装](#linux-安装) |
| Windows，原生运行 | [切换到 windows 分支的 Windows 教程](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/windows/docs/INSTALL_WINDOWS_CN.md) |

`master` 分支运行于 macOS 和 Linux。Windows 请下载 `windows` 分支，使用该分支的安装程序。

## macOS 安装

### 1. 安装 Python 和 Node.js

1. 打开 [Python macOS 下载页](https://www.python.org/downloads/macos/)，选择 **Python 3.13** 的 macOS installer，下载后双击 `.pkg`，按默认选项安装。
2. 在“应用程序 → Python 3.13”里双击 **Install Certificates.command**，等待完成后关闭该窗口。这是 [Python 官方安装步骤](https://docs.python.org/3.13/using/mac.html#installation-steps)的一部分。
3. 打开 [Node.js 下载页](https://nodejs.org/en/download)，选择 **LTS**、**macOS** 和 **Installer (.pkg)**，下载后双击安装。
4. 重新打开“终端”（可按 `Command + 空格`，搜索“终端”）。依次粘贴以下命令，每行按回车执行：

```bash
python3 --version
node --version
npm --version
```

Python 需要 **3.11 或更高**，Node.js 需要 **22.12 或更高**。建议先使用 Python 3.13；若版本不符，重新安装上面的版本并重开终端。

### 2. 下载 Cloudra

打开 [Cloudra 项目主页](https://github.com/yyywaa/Cloudra-mechanism-agent/tree/master)，点击绿色 **Code → Download ZIP**，解压后把文件夹放到准备长期保留的位置，例如“文稿”。这种方式不需要安装 Git。

### 3. 安装并启动

在 Cloudra 文件夹中双击 **Install.command**，等待安装完成。首次打开如果被系统拦截，确认下载来自本仓库后，到“系统设置 → 隐私与安全性”中选择“仍要打开”，按提示确认；见 [Apple 的打开说明](https://support.apple.com/zh-cn/102445)。

安装程序自动创建项目内的 `.venv`、安装 Python 和 JavaScript 依赖、构建网页，并在桌面创建 **Cloudra.command**。无需手动激活环境，也无需在安装时填写模型配置。

双击桌面上的 **Cloudra.command**，服务启动后浏览器会自动打开。**使用期间保留它打开的终端窗口。**

如果需要从终端安装：输入 `cd `（`cd` 后留一个空格），把解压后的 **Cloudra 文件夹**拖进终端，再按回车，然后依次执行：

```bash
bash install.sh
bash web.sh
```

## Linux 安装

### 1. 安装基础软件

Ubuntu 24.04 及更新版本：打开终端，执行下面两行。`sudo` 可能要求输入系统密码，输入时不显示字符是正常的。

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
```

打开 [Node.js 官方下载页](https://nodejs.org/en/download)，选择 **LTS → Linux → nvm → npm**，按页面显示的命令安装 Node.js。随后重新打开终端，检查：

```bash
python3 --version
node --version
npm --version
```

Python 需要 **3.11 或更高**，Node.js 需要 **22.12 或更高**。不要直接使用旧发行版仓库中的低版本 Node.js。其他 Linux 发行版通过自己的包管理器准备 Python、venv 和 Git，再按上述 Node.js 官方页面安装。

### 2. 下载并安装 Cloudra

```bash
git clone --branch master https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent
bash install.sh
bash web.sh
```

安装程序自动准备运行环境和网页，并创建应用菜单中的 **Cloudra**；如果系统已有桌面目录，也会创建桌面的 **Cloudra.desktop**。

以后从应用菜单点击 Cloudra，或双击桌面入口。桌面环境若提示入口不受信任，右键选择“允许启动”；也可直接在项目目录运行 `bash web.sh`。**服务运行时保留终端窗口。** 没有桌面环境的服务器请参考[远程访问配置](CONFIGURATION_CN.md)。

## 第一次打开界面

1. 在全局设置（Global Settings）中配置主 Agent 和协作 Agent 的模型、接口地址及凭据，也可使用界面提供的账号登录。
2. 创建项目，选择工作目录，放入结构或已有文件，输入任务后开始使用。
3. 需要量子化学计算时，再安装并配置相应计算软件与本地或远端节点，见[配置指南](CONFIGURATION_CN.md)和[部署文档](README.md#部署与配置)。

安装程序不会安装 ORCA、Gaussian、xTB、CREST，也不包含这些软件的许可证。普通对话、查文献和写代码可以先配置模型开始使用。

## 启动、停止与更新

日常启动：点击桌面入口；也可以进入项目目录执行：

```bash
bash web.sh
```

只关闭浏览器标签页不会停止服务。停止 Cloudra 时，在启动终端按 `Ctrl + C`；如需停止整个 Cloudra 服务，在项目目录另开终端执行：

```bash
.venv/bin/python -m cloudra stop
```

Cloudra 服务的停止与量子化学作业取消是不同操作；不要用关闭启动窗口来取消计算。

通过 Git 下载的用户，停止 Cloudra 后，在项目目录更新：

```bash
git pull --ff-only
bash install.sh
```

使用 ZIP 下载的用户，下载并解压新 ZIP 到新的长期目录，在新目录重新运行 `bash install.sh`，用它生成的新桌面入口启动。新目录中重新安装需要的可选依赖；确认原项目文件及自定义存储位置都保留后，再处理旧目录。不要把旧 `.venv` 复制到新目录。

## 常见问题

| 现象 | 处理方法 |
| --- | --- |
| 找不到 Python、Node.js 或 npm，或版本过低 | 完成上面的安装后重新打开终端，再运行版本检查。 |
| 已有新 Python，但 `python3` 仍指向旧版 | 在项目目录执行 `CLOUDRA_PYTHON=python3.13 bash install.sh`，明确选择已安装的 Python 3.13。 |
| 安装下载失败 | 查看终端中最后一条错误，确认可以访问 Python 包源和 npm 后，重新执行 `bash install.sh`。 |
| 浏览器没有自动打开，或页面提示未授权 | 复制终端里 `web UI:` 后面的完整链接到浏览器，包含 `#token=` 部分。端口可能不是 8000。 |
| 桌面入口丢失 | 在项目目录执行 `.venv/bin/python scripts/create_desktop_shortcut.py` 重新创建。 |
| 移动目录后无法启动 | 在新位置删除 `.venv`，重新运行 `bash install.sh`；安装环境和桌面入口都需要重新生成。 |

基础安装包含运行界面和 Agent 所需的依赖。需要额外的化学、PDF 或浏览器工具时，在项目目录按需安装：

```bash
.venv/bin/python -m pip install -e '.[chem,pdf,browser]'
.venv/bin/python -m playwright install chromium
```

这些可选包在不同平台上的可用性不同；某项安装失败时按报错处理，不影响已经完成的基础安装。PyMOL 需要另行安装。
