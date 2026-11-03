# Install Cloudra and start it from your desktop

[中文](INSTALL_CN.md) · [Project home](../README.md)

After installation, double-click the desktop launcher to start Cloudra and open its browser interface. The first installation downloads dependencies; you configure your model account in the interface afterwards.

| Your system | Start here |
| --- | --- |
| macOS, Apple Silicon or Intel | [macOS installation](#macos-installation) |
| Linux; the commands below use Ubuntu 24.04 or newer | [Linux installation](#linux-installation) |
| Windows, running natively | [Windows guide on the windows branch](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/windows/docs/INSTALL_WINDOWS.md) |

The `master` branch runs on macOS and Linux. For Windows, download the `windows` branch and use its installer.

## macOS installation

### 1. Install Python and Node.js

1. Open [Python downloads for macOS](https://www.python.org/downloads/macos/), find a **Python 3.13** macOS installer, download the `.pkg`, and install it with the default options.
2. In **Applications → Python 3.13**, double-click **Install Certificates.command** and wait for it to finish. This is part of the [official Python installation instructions](https://docs.python.org/3.13/using/mac.html#installation-steps).
3. Open [Node.js downloads](https://nodejs.org/en/download), choose **LTS**, **macOS**, and **Installer (.pkg)**, then download and run the installer.
4. Open a new Terminal window: press `Command + Space` and search for “Terminal”. Paste these commands one at a time, pressing Return after each:

```bash
python3 --version
node --version
npm --version
```

You need **Python 3.11 or newer** and **Node.js 22.12 or newer**. Python 3.13 is the recommended starting point. If a version is too old, install the version described above and reopen Terminal.

### 2. Download Cloudra

Open the [Cloudra repository](https://github.com/yyywaa/Cloudra-mechanism-agent/tree/master), click the green **Code → Download ZIP**, and unzip it. Move the extracted folder somewhere you intend to keep it, such as Documents. Git is not required for this method.

### 3. Install and start

Double-click **Install.command** inside the Cloudra folder and wait for installation to finish. If macOS blocks the first launch, confirm you downloaded it from this repository, then open **System Settings → Privacy & Security → Open Anyway** and confirm as prompted. See [Apple’s instructions](https://support.apple.com/en-us/102445).

The installer creates a local `.venv`, installs the Python and JavaScript dependencies, builds the interface, and creates **Cloudra.command** on your desktop. You do not need to activate the environment or enter model settings during installation.

Double-click **Cloudra.command** on your desktop. The service starts and opens your browser. **Keep the Terminal window it opens running while using Cloudra.**

To install from Terminal instead, type `cd ` with a space after `cd`, drag the extracted **Cloudra folder** into the window, and press Return. Then run:

```bash
bash install.sh
bash web.sh
```

## Linux installation

### 1. Install the prerequisites

On Ubuntu 24.04 or newer, open Terminal and run these two commands. `sudo` may ask for your system password; it is normal for no characters to appear as you type it.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip curl
```

Open the [official Node.js download page](https://nodejs.org/en/download), choose **LTS → Linux → nvm → npm**, and follow the installation commands displayed there. Open a new terminal afterwards and check:

```bash
python3 --version
node --version
npm --version
```

You need **Python 3.11 or newer** and **Node.js 22.12 or newer**. Avoid an older Node.js version from your distribution's repositories. On another Linux distribution, use its package manager to install Python, venv support and Git, then follow the same official Node.js download page.

### 2. Download and install Cloudra

```bash
git clone --branch master https://github.com/yyywaa/Cloudra-mechanism-agent.git
cd Cloudra-mechanism-agent
bash install.sh
bash web.sh
```

The installer prepares the runtime and interface, and adds **Cloudra** to the application menu. If your system has a desktop directory, it also creates **Cloudra.desktop** there.

For later starts, click Cloudra in the application menu or double-click its desktop launcher. If your desktop marks it as untrusted, right-click and choose **Allow Launching**. You can also run `bash web.sh` from the project directory. **Keep the service's terminal open.** For a server without a desktop, see [remote access configuration](CONFIGURATION.md).

## First use

1. In **Global Settings**, configure the coordinator and follower models, endpoint and credentials, or use the account login offered by the interface.
2. Create a project, choose a working directory, add structures or existing files, and describe your task.
3. When you need quantum-chemistry calculations, install the relevant software and configure your local or remote compute nodes. See [Configuration](CONFIGURATION.md) and the [deployment guides](README_EN.md#deployment-and-configuration).

The installer does not install ORCA, Gaussian, xTB or CREST, or supply their licenses. You can start with a model account for conversation, literature searches and coding.

## Start, stop and update

For everyday use, click the desktop launcher or run this from the project directory:

```bash
bash web.sh
```

Closing a browser tab leaves the service running. Press `Ctrl + C` in the launch terminal to stop the web service. To stop all Cloudra services, open another terminal in the project directory and run:

```bash
.venv/bin/python -m cloudra stop
```

Stopping Cloudra services and cancelling quantum-chemistry jobs are separate actions. Do not use the launch window to cancel calculations.

If you downloaded with Git, stop Cloudra, then update from the project directory:

```bash
git pull --ff-only
bash install.sh
```

If you downloaded a ZIP, download and extract a new copy into a new permanent directory. Run `bash install.sh` there and use its newly generated desktop launcher. Reinstall any optional dependencies in the new directory. Keep the old directory until you have preserved your project files and any custom storage locations. Do not copy the old `.venv` into the new directory.

## Common problems

| Problem | What to do |
| --- | --- |
| Python, Node.js or npm is missing or too old | Finish the prerequisite installation, reopen Terminal, and check the versions again. |
| A new Python is installed, but `python3` still selects an old version | Run `CLOUDRA_PYTHON=python3.13 bash install.sh` from the project directory to select your installed Python 3.13 explicitly. |
| A dependency download fails | Read the final error in Terminal, check access to the Python package index and npm, then rerun `bash install.sh`. |
| The browser does not open, or the page says it is unauthorized | Copy the complete URL after `web UI:` in Terminal, including its `#token=` fragment. The port may differ from 8000. |
| The desktop launcher is missing | Run `.venv/bin/python scripts/create_desktop_shortcut.py` from the project directory. |
| Cloudra stops launching after moving its folder | Remove `.venv` at the new location and rerun `bash install.sh` to recreate the environment and launchers. |

The basic installation includes the interface and Agent runtime. For additional chemistry, PDF or browser tools, install the optional packages you need from the project directory:

```bash
.venv/bin/python -m pip install -e '.[chem,pdf,browser]'
.venv/bin/python -m playwright install chromium
```

Availability of optional packages varies by platform. If one fails, follow its error message; the basic installation remains available. Install PyMOL separately.
