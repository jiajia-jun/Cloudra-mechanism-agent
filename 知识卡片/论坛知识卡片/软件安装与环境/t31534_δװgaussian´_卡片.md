---
key: t31534
title: ������δ��װgaussian����´�gview������'gaussian is not install'����
url: http://bbs.keinsci.com/thread-31534-1-1.html
domain: 软件安装与环境
source: keinsci
year: 2022
cards: 8
---

# ������δ��װgaussian����´�gview������'gaussian is not install'���� — 知识卡片

## 1. 使用笔记本运行 GaussView 的前提

在 Linux 系统下的笔记本电脑上使用 GaussView 查看分子结构时，仅安装 GaussView 即可满足需求，无需安装 Gaussian 进行计算。

---

## 2. 未安装 Gaussian 时的 GaussView 报错

在未安装 Gaussian 的情况下启动 GaussView 时，系统可能会弹出提示框显示“gaussian is not install”。

---

## 3. 解决 GaussView 报错的第一步：创建目录结构

为了解决未安装 Gaussian 导致的 GaussView 启动报错问题，需在 GaussView 同级目录下创建一个名为 g16 的文件夹。

---

## 4. 解决 GaussView 报错的第二步：创建子目录

在新建的 g16 文件夹内，需要继续创建两个子目录，分别命名为 scratch 和 bsd。

---

## 5. 解决 GaussView 报错的第三步：放置可执行文件

在 g16 目录下需放置一个名为 g16 的可执行文件，该文件大小约为 418.59 KB。

---

## 6. 解决 GaussView 报错的第四步：放置环境配置文件

在 bsd 目录下需创建并放置一个名为 g16.profile 的配置文件，该文件大小约为 1.94 KB。

---

## 7. 配置环境变量

在 ~/.bashrc 文件中需添加三行配置语句，分别设置 g16root 根目录为 /opt/、Gaussian 临时文件目录为 /opt/g16/scratch，并引入环境配置文件 source /opt/g16/bsd/g16.profile。

---

## 8. 设置目录权限

切换至 /opt/g16 目录后，建议执行 chmod 750 -R * 命令以设置相关权限。
