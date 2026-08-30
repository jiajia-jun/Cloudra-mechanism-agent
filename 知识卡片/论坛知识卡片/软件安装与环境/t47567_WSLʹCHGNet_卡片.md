---
key: t47567
title: WSL��ʹ��CHGNet
url: http://bbs.keinsci.com/thread-47567-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 7
---

# WSL��ʹ��CHGNet — 知识卡片

## 1. CHGNet 计算加速

CHGNet 可用于结构优化以加速 VASP 计算，在包含分子动力学计算的场景下效果显著。该工具在 Windows 环境下建议结合 WSL (如 Ubuntu-22.04) 使用。

---

## 2. CHGNet 与 LAMMPS 结合

CHGNet 支持与 LAMMPS 结合使用，相关的使用教程和讨论可在相关计算化学论坛及技术博客中获取。官方文档和资源可通过 chgnet.lbl.gov 进行查阅。

---

## 3. Windows 环境下 WSL 的安装

在 Windows 系统下使用 CHGNet 前需配置 WSL 环境，推荐安装 Ubuntu-22.04 版本。具体的安装步骤可参考相应的技术指南文档。

---

## 4. pip 安装 chgnet 包

安装 chgnet 需使用 pip 工具，执行 `pip install chgnet` 命令进行安装。若系统中尚未安装 pip，需先查阅相关教程完成 pip 的部署。

---

## 5. CHGNet 使用方法与脚本参考

安装完成后可查阅官方 Usage 部分获取基础使用方法。若需实现自动保存优化后的 final structure 并导出为 POSCAR 文件，可参考或修改由 AI 生成的脚本。此类脚本通常会读取当前目录下的 POSCAR 文件，进行优化后输出为 opt.poscar。

---

## 6. numpy 版本兼容性报错

在使用部分参考脚本（特别是仅针对 Structure Optimization 的脚本）时，可能会遇到 numpy 数据类型相关的报错。解决方法是按照报错提示或文档说明重新安装兼容版本的 numpy。

---

## 7. CHGNet 计算性能表现

CHGNet 的优化速度显著快于 VASP 直接计算，对于包含 90 个原子的体系，优化过程可在 5 秒内完成。使用 CHGNet 进行预处理可大幅节省计算时间，建议在结构优化流程中结合 ChatGPT 等工具辅助编写或修改脚本以提高效率。
