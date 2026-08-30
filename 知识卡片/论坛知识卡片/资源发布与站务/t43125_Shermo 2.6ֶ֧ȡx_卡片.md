---
key: t43125
title: Shermo 2.6��������֧�ֶ�ȡxtb������ļ���������ѧ��
url: http://bbs.keinsci.com/thread-43125-1-1.html
domain: 资源发布与站务
source: keinsci
year: 2024
cards: 3
---

# Shermo 2.6��������֧�ֶ�ȡxtb������ļ���������ѧ�� — 知识卡片

## 1. Shermo 2.6版本更新

Shermo 2.6版本已发布，主要更新在于增加了对xtb程序的支持，从而能够结合xtb进行热力学化学计算。
该版本兼容最新的xtb 6.6.1版本，且后续更新的xtb版本通常也支持此功能。

---

## 2. xtb输出文件重定向

Shermo通过读取xtb程序生成的伪Gaussian输出文件（通常命名为g98.out）来提取热力学数据。
在命令行中执行xtb计算时，可以通过重定向符号将输出写入g98.out文件（例如使用命令：xtb kastoria.xyz --ohess > kastoria.out）。

---

## 3. 电子能量缺失处理

xtb输出的g98.out文件中通常不包含电子能量信息，且无法通过settings.ini参数进行补充。
若未在运行Shermo时使用-E参数提供电子能量，程序将报错或无法完成计算。
