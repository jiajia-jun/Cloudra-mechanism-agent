---
key: t58734
title: XYZRender Web App �� ����ͼ�ι���վ
url: http://bbs.keinsci.com/thread-58734-1-1.html
domain: 可视化与制图
source: keinsci
year: 2026
cards: 6
---

# XYZRender Web App �� ����ͼ�ι���վ — 知识卡片

## 1. xyzrender 简介

xyzrender 是一款基于 Web 的渲染引擎，能够将化学结构文件渲染为高质量的矢量图或栅格图。
- 支持的输出格式包括 SVG、PNG、PDF 和 GIF。
- 该工具提供了本地化的 Web 应用程序界面，便于用户通过浏览器进行操作。

---

## 2. 目录结构说明

xyzrender-webapp 项目包含特定的目录结构以支持应用运行和文件管理。
- `xyzrender_app/` 是主目录，包含 `app.py`（Flask 服务程序）和 `requirements.txt`（Python 依赖列表）。
- `templates/` 目录包含前端文件 `index.html`。
- `MOLECULES/` 目录用于存放待处理的分子文件，`FIGURE/` 目录用于存放自动生成的渲染结果。

---

## 3. 基础安装命令

安装 xyzrender 的基础版本可直接使用 pip 命令或从 GitHub 仓库安装开发版。
- 基础安装命令为 `pip install xyzrender`。
- 安装最新开发版本的命令为 `pip install --upgrade git+https://github.com/aligfellow/xyzrender.git`。

---

## 4. 功能扩展安装

xyzrender 支持通过 extras 参数安装额外功能以支持特定输入文件类型。
- 安装晶体结构支持（适用于 VASP/QE 周期性结构及 phonopy）的命令为 `pip install xyzrender[crystal]`。
- 支持 SMILES 输入（依赖 rdkit）的命令为 `pip install xyzrender[smi]`。
- 支持 CIF 输入（依赖 ase）的命令为 `pip install xyzrender[cif]`。
- 安装所有上述功能的命令为 `pip install xyzrender[all]`。

---

## 5. 启动 Web 应用

启动 xyzrender 的本地 Web 服务需在项目目录下运行指定的 Python 脚本。
- 启动命令为 `python app.py`。
- 服务启动后，可通过浏览器访问 `http://localhost:5000` 进行使用。

---

## 6. 文件上传方式

用户可以通过文件系统操作或 Web 界面上传待渲染的分子结构文件。
- 可直接将分子文件放入 `MOLECULES/` 文件夹中。
- 也可以在 Web 页面通过拖拽的方式进行文件上传。
