---
key: t12509
title: xtb�е�GFN-xTB 1������ԭ���Ŵ�ʱ��Ȼ������
url: http://bbs.keinsci.com/thread-12509-1-1.html
domain: 量子化学方法
source: keinsci
year: 2019
cards: 6
---

# xtb�е�GFN-xTB 1������ԭ���Ŵ�ʱ��Ȼ������ — 知识卡片

## 1. xtb 默认 GFN 版本与参数设置

xtb 软件默认的 GFN 方法已更新为 GFN2-xTB。若需使用旧版本的 GFN-xTB 1，需在命令行添加 `--gfn 1` 选项。对于部分团簇结构计算，使用 GFN-xTB 1 可能会获得更优结果。

---

## 2. molclus 与 genmer 的功能及获取方式

molclus 及其组件 genmer 可用于结构搜索与构型生成。相关工具可通过指定网址 http://www.keinsci.com/research/molclus.html 下载获取。

---

## 3. molclus 基础输入文件格式

molclus 运行需要配置 settings.ini 文件，其中需定义 rmin 和 rmax 参数。示例配置中设定 `30 rmin 4 rmax 5.5`，并指定输入文件为 `examples/Li.xyz`。

---

## 4. xtb 与 molclus 联用的 SCF 收敛问题

在使用 molclus 调用最新版 xtb 进行计算时，可能会出现 SCF 不收敛导致程序报错终止的情况。

---

## 5. GFN-xTB 1 解决 SCF 不收敛问题

当遇到 xtb 计算 SCF 不收敛问题时，在 molclus 的 settings.ini 中将 xtb_arg 参数设置为 `--gfn 1` 可解决该问题。此操作强制程序使用 GFN-xTB 1 方法进行计算。

---

## 6. xtb 方法对团簇结构优化的影响

针对高度无序的初始结构，使用 molclus 配合 xtb 的 GFN-xTB 1 方法可以有效地优化出合理的团簇结构。相比之下，GFN2-xTB 虽在原子力场方面表现更优，但在此类复杂团簇的几何优化中可能不如 GFN-xTB 1 稳定。
