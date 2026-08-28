---
id: 692
title: 几种基于核酸序列构建三维结构的工具
url: http://sobereva.com/692
domain: 可视化与制图
topic: 基于核酸序列构建DNA_RNA三维结构工具
cards: 6
---

# 基于核酸序列构建DNA_RNA三维结构工具 — 知识卡片

## 1. 在线工具DNA Sequence to Structure

用户在网页 http://www.scfbio-iitd.res.in/software/drugdesign/bdna.jsp 输入DNA序列及DNA结构类型，可立即在线获得返回的PDB格式三维结构文件。该工具操作简便，无需本地安装程序，适合快速生成标准DNA模型。

---

## 2. 在线工具web.x3dna.org构建混合构象DNA

用户访问 http://web.x3dna.org 并选择 Rebuilding - combination of A-, B-, or C-form DNA models，可设置多段DNA序列并分别指定每段的构象形式。例如设置三段分别为AAA（A-DNA）、CCCC（B-DNA）、GGG（C-DNA），提交后即可下载生成的PDB文件。

---

## 3. AmberTools组件NAB的使用流程

NAB是AmberTools程序包中的组件，下载地址为 http://ambermd.org。最简单的运行方式为 `nab test.nab -o test.out`，该命令会将输入文件test.nab编译成名为test.out的可执行程序，执行 `./test.out` 即可运行其中的指令。

---

## 4. NAB程序生成DNA/RNA结构的参数设置

NAB通过 `fd_helix` 函数生成核酸结构，该函数包含三个参数：第一个参数控制核酸类型（如"abdna"），第二个参数输入序列（如"gcgttaacgc"），第三个参数指定分子类型（填"dna"生成DNA或"rna"生成RNA）。运行生成的可执行文件后，DNA骨架将沿着Z轴延伸。

---

## 5. Gabedit构建核酸结构及添加抗衡离子

用户在Gabedit（下载地址 http://gabedit.sourceforge.net）中点击菜单栏 Geometry - Draw，右键选择 Build - polyNucleic Acid，通过点击碱基按钮交互式生成三维结构。构建过程中可自定义核酸类型和结构形式，若勾选 Add Counter Ion 选项，程序会自动在磷酸基旁添加Na+作为抗衡离子。

---

## 6. Avogadro插入DNA/RNA结构

用户在Avogadro（下载地址 http://avogadro.cc）中点击菜单栏 Build - Insert - DNA/RNA，在弹出的窗口中输入核酸序列即可在图形窗口实时观察生成的结构。该工具支持自由选择DNA和RNA、单链和双链以及不同的结构形式。
