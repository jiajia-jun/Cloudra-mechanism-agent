---
key: t59845
title: ʹ��atompaw������VASP��ʽ���Ƶ�EOS������֤
url: http://bbs.keinsci.com/thread-59845-1-1.html
domain: 其他量化软件
source: keinsci
year: 2026
cards: 7
---

# ʹ��atompaw������VASP��ʽ���Ƶ�EOS������֤ — 知识卡片

## 1. AtomPAW 生成赝势

AtomPAW 软件可用于生成全电子参考波函数，进而构建 VASP 格式的 PAW 赝势。该工具支持生成从 1 到 96 号元素的赝势文件。

---

## 2. 莫尔斯势标准

此次生成的 PAW 赝势以莫尔斯势作为交换关联势的标准。该标准被应用于当前发布的赝势数据集中。

---

## 3. 赝势数据集来源与标签

该赝势数据集托管于 MaterialsCloud 平台，其镜像地址为 https://dspaw.dftpaw.tech。数据集的标签为 XH-PAW26，势能可视化图像标识为 DS-PAW@PW|XH-PAW26。

---

## 4. 赝势文件格式

生成的 PAW 赝势文件格式与 DS-PAW 保持一致。该格式兼容 QE、Abinit 和 pwpaw 等计算软件。

---

## 5. VASP 格式兼容性

目前生成的 PAW 赝势已使用 VASP 和 DS-PAW 进行了测试。测试内容涵盖不同类型的赝势以确保其与 VASP 格式的兼容性。

---

## 6. 软件授权说明

由于 VASP 的商业授权限制及其禁止对第三方生成势函数进行直接比较的规定，相关测试结果仅使用 DS-PAW 展示。

---

## 7. XH-PAW26 覆盖范围

XH-PAW26 赝势数据集目前覆盖了 1 至 96 号元素。这些元素的数据已完成构建并可供使用。
