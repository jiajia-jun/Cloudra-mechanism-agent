---
key: t19003
title: Gaussian-ORCA-xTB���ý���ONIOM����
url: http://bbs.keinsci.com/thread-19003-1-1.html
domain: Gaussian使用
source: keinsci
year: 2020
cards: 7
---

# Gaussian-ORCA-xTB���ý���ONIOM���� — 知识卡片

## 1. ONIOM 方法的扩展接口应用

ONIOM 方法可以通过接口进行扩展，从而调用 Gaussian 之外的其他程序。该接口允许对底层脚本进行微调，以适应不同区域或不同外部程序的调用需求。通过这种方式，用户可以在 ONIOM 框架下整合多种计算化学软件的功能。

---

## 2. 外部脚本路径配置

在使用外部脚本进行 ONIOM 计算前，必须将 `orca.sh` 中的 `orcapath` 修改为用户本机 ORCA 程序的实际安装路径。若路径配置不正确，计算过程中程序将无法找到可执行文件从而导致报错。

---

## 3. Gaussian 与 xTB 的 ONIOM 联用示例

Gaussian 可以通过 ONIOM 模块调用外部 xTB 程序进行计算。对应的 Gaussian 输入文件关键字设置如下：
```
%nproc=1
#P ONIOM(B3LYP/def2SVP em=GD3BJ : External="sh ./xtb.sh") Opt(nomicro)
```
该设置指定高层方法为 B3LYP/def2SVP 并包含 GD3BJ 色散校正，低层方法通过执行 `sh ./xtb.sh` 脚本调用 xTB。

---

## 4. Gaussian 与 ORCA 的 ONIOM 联用示例

ONIOM 计算可将 ORCA 作为外部程序调用，结合 UFF 力场使用。对应的 Gaussian 输入文件关键字设置如下：
```
%nproc=1
#P ONIOM(External="sh ./orca.sh" : uff) Opt(nomicro)
```
此设置指定高层方法为外部 `sh ./orca.sh` 脚本（即 ORCA），低层方法为 UFF 力场。

---

## 5. Gaussian、ORCA 与 xTB 的三层次 ONIOM 联用

ONIOM 支持同时调用 ORCA 和 xTB 两个外部程序构建三层模型。对应的 Gaussian 输入文件关键字设置如下：
```
%nproc=1
#P ONIOM(External="sh ./orca.sh" : External="sh ./xtb.sh") Opt(nomicro)
```
该命令设置了两个外部接口，分别用于 ONIOM 的不同层次计算。

---

## 6. 标准 Gaussian 内置 ONIOM 优化示例

除调用外部程序外，ONIOM 也可以完全使用 Gaussian 内置的方法进行几何优化。一个标准的双层 ONIOM 优化输入示例如下：
```
#P ONIOM(B3LYP/6-31G(d,p):UFF) Opt
```
该示例使用 B3LYP/6-31G(d,p) 作为高层方法，UFF 作为低层方法。

---

## 7. 多重外部接口调用效果

通过接口实现多重外部程序调用（如 Gaussian-ORCA-xTB），经测试运行顺畅，表明该方法的联用方案在技术上具备可行性。这种多层次的混合计算方式能够有效结合不同软件的优势。
