---
key: t59443
title: ChemSSH���������㻯ѧSSH����̨��ԭChemweb��
url: http://bbs.keinsci.com/thread-59443-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2026
cards: 15
---

# ChemSSH���������㻯ѧSSH����̨��ԭChemweb�� — 知识卡片

## 1. ChemSSH 项目定位与架构

ChemSSH 是基于原 Chemweb 平台开发的远程服务器管理工具，旨在提供简洁、高效的 SSH 连接方案。该项目后端使用 FastAPI 框架构建，通过 SSH 端口转发实现对远程服务器的管理和数据交互。

---

## 2. ChemSSH 界面布局与功能分区

ChemSSH 的工作界面分为三个主要区域，左侧为远程文件管理器，中间为终端，右侧为结构预览面板。这种布局支持对文件、终端命令和可视化结构的同步操作与监控。

---

## 3. ChemSSH 文件管理功能

左侧文件管理器支持多选和拖拽上传/下载文件，具备文件搜索功能。双击文件可进行文本或结构预览，且集成了 ASE 库用于解析和展示结构文件。

---

## 4. ChemSSH 文件编辑与状态恢复

文件管理器支持直接调用编辑器打开不同文件进行修改，并能保留文件的编辑状态。Launcher 功能支持直接打开不同编辑状态下的文件，便于切换工作上下文。

---

## 5. ChemSSH 终端交互功能

中间的终端区域用于执行命令行操作，支持与文件管理器在相同的目录下同步运行文件。终端具备双击同步目录功能，并集成了 sz/rz 工具用于文件的上传和下载。

---

## 6. ChemSSH 结构预览与数据解析

右侧面板支持文本和结构预览，集成 cclib 库用于解析计算输出文件。cclib 支持解析 Gaussian 等程序的格式，能够展示结构和轨迹信息，并支持通过 WebSocket 实现解析进度的实时推送。

---

## 7. ChemSSH 结构可视化交互细节

结构预览功能支持获取并显示 Fmax 信息，可展示原子序数，具备 Wrap 展示功能以及播放轨迹功能。渲染过程采用了 Floyd-Steinberg 算法 + FP32 省空间 + brotli 压缩技术，以提升大结构信息的加载和渲染效率。

---

## 8. ChemSSH 硬件加速与界面特性

结构渲染支持利用 GPU 硬件加速，文本编辑器支持全屏模式。界面文件管理器支持双击将项目目录设置为工作目录。

---

## 9. ChemSSH 无边框窗口模式

ChemSSH 提供无边框窗口模式，支持浏览器登录、移动端访问以及自定义窗口绑定关系。在此模式下，双击文件可自动打开新窗口进行预览。

---

## 10. ChemSSH-launcher 项目定位

ChemSSH-launcher 是配套的客户端启动器，提供 Windows 便携版和 Webview 版本。该工具使用 Go 语言编写，无需安装复杂依赖，默认支持开机自启动。

---

## 11. ChemSSH-launcher 安全存储与连接

Webview 版本依赖 Webview2 组件，支持手动启动。ChemSSH-launcher 可在本地安全存储 Windows 凭据和 SSH 连接信息，避免重复输入，且支持管理多个远程服务器。

---

## 12. ChemSSH-launcher 安装注意事项

安装 ChemSSH-launcher 后需重启电脑或注销以确保生效。启动时建议使用管理员权限，若在非安装目录运行，需注意当前路径问题。

---

## 13. ChemSSH-launcher 端口管理功能

客户端支持本地端口占用自动检测，具备停止端口转发功能。此外，还提供停止转发并关闭服务器的组合操作，并能通过不同标签页管理不同的连接会话。

---

## 14. ChemSSH-launcher SFTP 支持

ChemSSH-launcher 内置 SFTP 功能，支持通过拖拽方式上传和下载文件。用户可直接在本地或远程端打开文件并保持编辑状态同步。

---

## 15. ChemSSH 相关资源下载

ChemSSH-launcher 和 ChemSSH 的相关资源及安装包（含所需的 Python 库）可在 GitHub Releases 页面下载。用户也可以选择从源码自行编译 ChemSSH-launcher。
