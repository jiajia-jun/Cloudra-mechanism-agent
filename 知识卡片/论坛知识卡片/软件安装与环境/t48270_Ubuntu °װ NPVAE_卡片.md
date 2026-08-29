---
key: t48270
title: Ubuntu �°�װ NPVAE
url: http://bbs.keinsci.com/thread-48270-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2024
cards: 10
---

# Ubuntu �°�װ NPVAE — 知识卡片

## 1. NP-VAE 简介

NP-VAE 是一个应用于计算化学和药物研发领域的 AI 工具。该工具通过学习分子结构以生成并优化分子，支持药物逆合成分析与药物发现过程。

---

## 2. Conda 安装包获取

Linux x86_64 系统可使用 wget 命令下载 Anaconda 安装脚本 `Anaconda3-2024.06-1-Linux-x86_64.sh`。具体命令为 `wget https://repo.anaconda.com/archive/Anaconda3-2024.06-1-Linux-x86_64.sh`。

---

## 3. Anaconda 安装执行

运行 `bash Anaconda3-2024.06-1-Linux-x86_64.sh` 命令可启动安装流程。安装过程中阅读用户协议后需输入 `yes` 并回车以同意条款，后续路径确认可直接按回车键。

---

## 4. Conda 环境初始化

安装完成后，若使用 Bash shell 需执行 `source ~/.bashrc`，若使用 Zsh shell 需执行 `source ~/.zshrc`。执行这些命令可使 conda 指令在当前终端生效。

---

## 5. NPVAE 项目下载

在 Conda 环境准备就绪后，使用 `git clone https://github.com/toshikiochiai/NPVAE` 命令可获取远程项目代码到本地。

---

## 6. Conda 环境创建与激活

进入项目目录下的 env 文件夹，使用 `conda env create -f npvae_env.yml` 命令依据预配置文件创建环境。创建完成后需执行 `conda activate npvae_env` 激活环境，每次重启终端后需重新激活。

---

## 7. NPVAE 运行目录准备

NPVAE 项目运行前需在项目目录下创建用于预处理的 `save_data`、`input_data`、`weights` 文件夹及用于训练的 `param_data` 文件夹。使用命令 `mkdir -p save_data/input_data/weights param_data` 可一次性完成创建。

---

## 8. 数据预处理命令

执行预处理脚本需指定 SMILES 文件路径和保存路径。示例命令为 `python preprocessing.py --smiles_path ./smiles_data/drugbank_smiles.txt --save_path ./save_data`。

---

## 9. 模型训练命令

启动模型训练需指定 SMILES 数据路径、预处理数据路径及模型参数保存路径。示例命令为 `python train.py --smiles_path ./smiles_data/drugbank_smiles.txt --prepared_path ./save_data --save_path ./param_data`。

---

## 10. GPU 状态监控命令

使用 `nvidia-smi` 命令可查看当前显卡的运行状态。该命令能显示显存占用、温度、功耗及 GPU 利用率等关键性能指标。
