# Install Cloudra and start it from your desktop

[中文](INSTALL_CN.md) · [Project home](../README.md)

Download the installer for your system, double-click it, then open Cloudra from your applications or desktop. Packages include Python, Node.js, core dependencies and the built interface. You do not need to install developer tools first.

| System | Package | Open after installation |
| --- | --- | --- |
| macOS, Apple Silicon | `Cloudra-<version>-macos-arm64.pkg` | Cloudra in Applications |
| macOS, Intel | `Cloudra-<version>-macos-x86_64.pkg` | Cloudra in Applications |
| Ubuntu / Debian desktop, x86_64 | `Cloudra-<version>-linux-x64.deb` | Cloudra in the application menu |
| Other compatible Linux desktops, x86_64 | `Cloudra-<version>-linux-x64.tar.gz` | Cloudra inside the extracted folder |
| Windows, native x64 | `Cloudra-<version>-windows-x64-Setup.exe` | Cloudra in the Start menu or desktop |

See the [Windows guide on the `windows` branch](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/windows/docs/INSTALL_WINDOWS.md) for Windows instructions. For development or your own deployment, see [Install from source](#install-from-source) below.

## Download a package

Packages are currently provided as GitHub Actions build artifacts and have not been published as formal Releases. A package becomes downloadable when its packaging workflow finishes successfully and uploads the artifact.

1. Sign into GitHub and open the repository's [Actions page](https://github.com/yyywaa/Cloudra-mechanism-agent/actions).
2. Select the packaging workflow for your system, then open a recent successful build of the branch you want.
3. Download the artifact for your system and architecture from **Artifacts** at the bottom of the page. Names are listed below.
4. Extract the downloaded outer ZIP to find the `.pkg`, `.deb`, `.tar.gz` or `Setup.exe` inside.

| System | Packaging workflow | Artifact name |
| --- | --- | --- |
| macOS | [macOS installer](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/package-macos.yml) | `Cloudra-macos-arm64` or `Cloudra-macos-x86_64` |
| Linux | [Linux desktop packages](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/package-linux.yml) | `Cloudra-linux-x64` |
| Windows | [Windows installer](https://github.com/yyywaa/Cloudra-mechanism-agent/actions/workflows/windows-installer.yml) | `windows-installer-x64` |

GitHub requires you to be signed in to download workflow artifacts; see [GitHub's instructions](https://docs.github.com/en/actions/how-tos/manage-workflow-runs/download-workflow-artifacts). If a package is unavailable, wait for a successful packaging run or [install from source](#install-from-source).

## Install on macOS

1. Open the Apple menu → **About This Mac**. For an Apple M-series chip, choose `arm64`; for an Intel processor, choose `x86_64`.
2. Double-click the `.pkg`, then follow **Continue** and **Install** in the system installer. macOS may request your administrator password.
3. Open Finder → **Applications** and double-click **Cloudra**. Its interface opens in your browser. An existing desktop directory also receives a Cloudra entry.
4. For later use, open Cloudra from Applications, the desktop or Dock. To stop it, right-click its Dock icon and choose **Quit**, or choose **Quit Cloudra** from the application menu.

Current test packages have not been signed with an Apple developer certificate or notarized. If macOS blocks one, first confirm it came from the intended project build, then open **System Settings → Privacy & Security**, find its message, and choose **Open Anyway**. Follow the confirmation prompt. The installer and app may each trigger this on first launch; see [Apple's instructions](https://support.apple.com/en-gb/102445).

The download also includes `Unblock-Cloudra.command`; see the [unblock instructions](../README.md#if-macos-blocks-the-first-launch).

## Install on Linux

Desktop packages target Ubuntu 22.04 or newer and Debian 12 or newer. On another distribution, try the portable archive.

### Ubuntu / Debian

Double-click the `.deb` and choose **Install** in your system's software installer. Enter your password if requested. Then search for **Cloudra** in the application menu and open it; the interface opens in your browser. The first launch adds a shortcut to an existing desktop directory. If marked as untrusted, right-click and choose **Allow Launching**.

If no graphical installer is associated with `.deb` files, open a terminal in the download directory and run:

```bash
sudo apt install ./Cloudra-*-linux-x64.deb
```

### Linux portable archive

The portable archive uses your desktop's `xdg-utils` and `lsof` packages; install them through your distribution's software manager if missing. The `.deb` declares these dependencies automatically.

Extract `.tar.gz` into a folder you intend to keep, then double-click the executable named **Cloudra** inside. The first launch adds an application-menu entry and, when a desktop directory exists, a desktop shortcut. Keep the extracted directory so these entries continue to work.

To stop Cloudra, right-click its application-menu entry and choose **Stop Cloudra**.

## First use and updates

1. In **Global Settings**, configure the coordinator and follower models, endpoint and credentials, or use the account login offered in the interface.
2. Create a project, choose a working directory, add structures or existing files, and describe your task.
3. When you need calculations, configure local or remote compute nodes. See [Configuration](CONFIGURATION.md) and the [deployment guides](README_EN.md#deployment-and-configuration).

Packages include the interface and core runtime. Install quantum-chemistry software such as ORCA, Gaussian, xTB or CREST, and obtain its licenses, separately as needed. Model calls and online features still need the relevant network access and account settings.

Closing a browser tab leaves Cloudra running; click the application entry again to reopen the interface. Stopping Cloudra services and cancelling quantum-chemistry jobs are separate actions.

To update, quit Cloudra and install a newer package for the same system and architecture. Extract a new portable version into a new permanent directory and launch it there. Preserve project files and custom data in the old directory before removing it.

For startup failures, read the system's error message. Logs are at `~/Library/Logs/Cloudra/desktop.log` on macOS and `~/.local/state/cloudra/desktop.log` on Linux.

## Install from source

These steps are for developers, users adding Python extensions and people managing their own deployments. The `master` source branch runs on macOS / Linux; native Windows uses the [`windows` branch](https://github.com/yyywaa/Cloudra-mechanism-agent/tree/windows).

### Prepare the environment

You need **Python ≥ 3.11**, **Node.js ≥ 22.12**, and npm. Python 3.13 and Node.js LTS are recommended starting points.

On macOS, install the Python 3.13 `.pkg` from [Python's downloads](https://www.python.org/downloads/macos/), then run **Applications → Python 3.13 → Install Certificates.command**. Install the macOS LTS `.pkg` from [Node.js](https://nodejs.org/en/download) and reopen Terminal.

On Ubuntu 24.04 or newer:

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
```

On the [official Node.js download page](https://nodejs.org/en/download), choose **LTS → Linux → nvm → npm** and follow its commands. Reopen your terminal. On another distribution, use its package manager to prepare Python, venv support and Git.

### Download, install and start

```bash
git clone --branch master https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent
bash install.sh
bash web.sh
```

You can also choose **Code → Download ZIP** on the project page and extract it into a permanent directory. On macOS, type `cd ` in Terminal, including the trailing space, drag the extracted folder into the window, and press Return. Then run the last two commands above. You can also double-click `Install.command` in the source directory to install.

The source installer creates `.venv`, installs Python and JavaScript dependencies, builds the interface and creates desktop entries. No manual environment activation or model configuration is needed during installation. When starting with `bash web.sh`, keep the launch terminal open.

To stop all services in a source installation:

```bash
.venv/bin/python -m cloudra stop
```

To update a Git checkout, stop Cloudra, run `git pull --ff-only` in the source directory, then run `bash install.sh` again. After moving a source directory, remove `.venv` at the new location and reinstall; the old virtual environment cannot simply be reused.

For additional chemistry, PDF or browser tools, install the optional packages you need from the source directory:

```bash
.venv/bin/python -m pip install -e '.[chem,pdf,browser]'
.venv/bin/python -m playwright install chromium
```

Install PyMOL separately. Availability of optional packages varies by platform; check the specific error if installation fails.

| Source installation problem | What to do |
| --- | --- |
| A newer Python is installed, but an old one is selected | Run `CLOUDRA_PYTHON=python3.13 bash install.sh`. |
| The desktop launcher is missing | Run `.venv/bin/python scripts/create_desktop_shortcut.py` to recreate it. |
| The browser does not open or says it is unauthorized | Copy the complete URL after `web UI:` in the launch terminal, including its `#token=` fragment. |
