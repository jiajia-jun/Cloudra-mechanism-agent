---
key: t52197
title: ��򵥵ģ�û��֮һ����MacOS������Multiwfn�ķ���
url: http://bbs.keinsci.com/thread-52197-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2025
cards: 13
---

# ��򵥵ģ�û��֮һ����MacOS������Multiwfn�ķ��� — 知识卡片

## 1. 在MacOS上运行Windows版Multiwfn的可行性

Multiwfn 可在 MacOS 系统上通过 Wine 兼容层运行，无需安装 Windows 虚拟机，从而节省系统资源。此方法适用于 Intel CPU 和 Apple Silicon (如 M1/M2) 架构的 Mac 电脑。

---

## 2. 准备工作：CrossOver 方式所需文件与软件

使用 CrossOver 方式需要下载官方提供的 Multiwfn Windows 64 位版本程序，并购买或下载 CrossOver 软件。CrossOver 是一个基于 Wine 的商业兼容层，相比自行搭建 Wine 环境更为简便，特别适合 Apple Silicon 芯片的 Mac 用户。

---

## 3. 准备工作：Wine 方式所需文件与软件

使用免费 Wine 方式需要从官网下载 Multiwfn Windows 64 位版本。Mac 上可通过 Homebrew 或 MacPorts 安装 Wine，若使用 Homebrew，需在终端执行 `brew install --cask --no-quarantine wine-stable` 命令。

---

## 4. CrossOver 安装 Multiwfn：创建容器

打开 CrossOver 软件，通过“容器”菜单选择“新建容器”，在创建向导中选择 Windows 10 64-bit 作为环境类型（也可选择 Windows 7/11），并将容器命名为“Multiwfn”。

---

## 5. CrossOver 安装 Multiwfn：复制程序文件

将解压后的 Multiwfn 文件夹内的所有文件复制到 CrossOver 虚拟的 C 盘目录中。

---

## 6. CrossOver 安装 Multiwfn：创建启动项

在 CrossOver 软件中进入“运行命令”菜单，定位到 C 盘下的 Multiwfn 文件夹，选择 `Multiwfn.exe`，并保存该命令配置以生成启动项。

---

## 7. CrossOver 安装 Multiwfn：完成与运行

安装配置完成后，在 MacOS 的 Launchpad 或应用程序列表中会出现 Multiwfn 的图标，点击该图标即可通过 CrossOver 启动程序。

---

## 8. Wine 安装 Multiwfn：放置文件

下载的 Multiwfn 程序文件建议放置在用户目录下，例如 `/Users/name/Multiwfn/`。

---

## 9. Wine 安装 Multiwfn：配置命令别名

为了方便在终端调用，需在 `.bash_profile` 文件中添加别名命令：`alias Multiwfn='wine /Users/name/Multiwfn/Multiwfn.exe'`。

---

## 10. Wine 安装 Multiwfn：运行与初始化

配置别名后，在终端输入 `Multiwfn` 即可启动程序。首次运行时 Wine 会自动安装一些必要的运行库，之后的启动将不再重复此过程，且支持拖拽文件到终端或使用 GUI 进行交互。

---

## 11. 更新 Multiwfn 版本的方法

在 MacOS 上使用 Wine 或 CrossOver 运行 Multiwfn 时，若要更新到新版本，只需下载最新的 Windows 版 `Multiwfn.exe` 文件并替换原有文件即可。

---

## 12. CrossOver 运行 Multiwfn 的优缺点

CrossOver 方式虽然收费且需要手动配置路径，但其对 Windows 软件的兼容性较好，通常可以正常运行 Multiwfn 的 GUI 界面。

---

## 13. 其他在 Mac 上通过 CrossOver 运行的化学软件

除 Multiwfn 外，CrysAlisPro、Origin、GaussView 6.1.1、Diamond、POV-Ray、Shelxle、Olex2 (Win) 等软件也可通过 CrossOver 在 Mac 上运行。部分软件如 Spartan 14 可能存在 Bug，而 SHIMADZU 的 LabSolution UV-Vis 等软件可能无法正常运行。
