---
key: t46184
title: sobtop����ʽ֧��GAFF2����
url: http://bbs.keinsci.com/thread-46184-1-1.html
domain: 分子动力学与力场
source: keinsci
year: 2024
cards: 5
---

# sobtop����ʽ֧��GAFF2���� — 知识卡片

## 1. Sobtop 支持 GAFF2 力场

Sobtop 1.0(dev4) 及以上版本已支持使用 GAFF2 力场生成拓扑文件。程序主页为 http://原作者.com/soft/Sobtop。用户可利用该功能将 GAFF2 应用于分子动力学模拟等计算场景。

---

## 2. GAFF2 文件配置步骤

将 Sobtop 目录下的 ATOMTYPE_GFF.DEF、bonded_param.dat 和 LJ_param.dat 备份。将 examples\GAFF2\ 目录中的 ATOMTYPE_GFF2.DEF、bonded_param.dat 和 LJ_param.dat 复制到 Sobtop 根目录下。需将 ATOMTYPE_GFF2.DEF 重命名为 ATOMTYPE_GFF.DEF。

---

## 3. GAFF2 参数文件来源说明

CORR_NAME_TYPE.DAT 和 ATOMTYPE_GFF2.DEF 取自 AmberTools 24。bonded_param.dat 和 LJ_param.dat 中的 GAFF2 参数对应 AmberTools 24 中的 GAFF2 参数文件 gaff2.dat。

---

## 4. Sobtop 生成 GAFF2 拓扑

完成文件配置后，运行 Sobtop 并指定相应的 GAFF 原子类型和参数类型即可生成 GAFF2 拓扑文件。程序将依据配置好的参数文件处理分子结构。

---

## 5. GAFF2 官方形式电荷限制

目前 GAFF2 尚未提供正式的形式电荷数据，因此在 Sobtop 中使用 GAFF2 需手动指定形式电荷。未来若 GAFF2 官方发布了形式电荷数据，Sobtop 将会直接支持并像 GAFF 一样自动处理。
