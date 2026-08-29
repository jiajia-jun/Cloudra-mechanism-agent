---
key: t55596
title: ʹ�ü��а崫�ݼ��νṹ��gview
url: http://bbs.keinsci.com/thread-55596-1-1.html
domain: Gaussian使用
source: keinsci
year: 2025
cards: 7
---

# ʹ�ü��а崫�ݼ��νṹ��gview — 知识卡片

## 1. xyzTrick 简介

xyzTrick 是一个用于解决 Gaussian 日志文件传输与预览问题的工具，旨在避免将大型 log 文件上传至服务器或下载到本地。该工具利用 Windows 剪贴板 API 监控数据，可将剪贴板中的 XYZ 格式数据直接转换为 Gaussian 日志文件，从而调用 GaussView 打开预览。

---

## 2. xyz_monitor.exe 使用方法

双击运行 xyz_monitor.exe 后，程序会在后台常驻并监听剪贴板内容。当用户复制数据集时，程序会自动获取剪贴板中的内容，将其转换为 Gaussian 日志文件格式，并尝试使用 GaussView 打开。

---

## 3. 支持的文件格式与操作

该工具支持多帧 XYZ 文件及仅含元素和坐标的标准 XYZ 文件（至少包含 4 个原子）。通过 VSCode 等编辑器粘贴坐标数据时，只需将 xyz 文件内容附加在 gjf 文件尾部，程序即可识别并预览数据集，无需额外的格式要求或 x y z 关键字。

---

## 4. 配置文件参数说明

首次运行时会在当前目录生成 config.ini 及 temp/、logs/ 文件夹。config.ini 中包含可自定义的选项，如热键设置（hotkey）、GaussView 执行文件路径（gview_path）、临时文件目录（temp_dir）、日志文件位置（log_file）、日志级别（log_level）、是否保存日志（log_to_file）、删除临时文件的等待时间（wait_seconds）、最大内存使用量（max_memory_mb）以及剪贴板字符限制（max_clipboard_chars）。

---

## 5. 配置文件修改与生效机制

修改 config.ini 配置文件后，必须向系统发送重载信号（reload）才能使更改生效。程序通过监听系统信号来动态更新配置，而非自动实时读取。

---

## 6. 剪贴板数据监控限制

目前版本可能不支持写入特殊的剪切板数据格式。若遇到无法预览的情况，建议直接通过标准的 xyz 文件内容进行复制操作。

---

## 7. 源代码与编译信息

源代码及 Makefile 已发布在 GitHub 页面。程序源码使用 C++ 编写，利用 Windows.h 提供的剪贴板 API 实现，编译时使用了 mingw 编译器。
