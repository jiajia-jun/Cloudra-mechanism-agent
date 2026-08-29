---
key: t23932
title: ��ORCA 4�������ļ�����ORCA 5��ʹ�õ�����ת���ű�
url: http://bbs.keinsci.com/thread-23932-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2021
cards: 11
---

# ��ORCA 4�������ļ�����ORCA 5��ʹ�õ�����ת���ű� — 知识卡片

## 1. ORCA 5.0 移除的关键字

ORCA 5.0 移除了 ORCA 4.x 中使用的部分关键字，包括 Grid、GridX、FinalGrid、FinalGridX、NoFinalGrid 和 NoFinalGridX。在 ORCA 5.0 中使用这些已被移除的关键字会导致报错。ORCA 5.0 针对积分网格（XC、COSX 数值积分精度）的控制策略发生了改变，旧版网格控制关键字不再适用。

---

## 2. ORCA 5.0 积分网格默认策略

ORCA 5.0 内部采取了更合理的数值积分策略，显著降低了人为指定网格的频率。结构优化等计算的积分网格使用更加智能。建议用户让 ORCA 5.0 自动选择网格策略，以获得最佳精度与效率的平衡。

---

## 3. 直接导入 ORCA 4 输入文件的处理

用户可以直接将 ORCA 4.0 使用过的输入文件导入 ORCA 5.0。虽然必须删除相关的网格控制关键字，但若用户期望保持与 ORCA 4.0 相同的精度，可以在 ORCA 5.0 中指定 project name 并观察自动生成的网格精度，以此评估 ORCA 5.0 默认设置的合理性。若默认精度不足，用户需手动进行调整。

---

## 4. 清除旧版关键字的 Bash 脚本

以下 Bash 脚本用于批量删除当前目录下 `.inp` 文件中的旧版网格关键字（Grid、GridX、FinalGrid、FinalGridX、NoFinalGrid、NoFinalGridX）：
```bash
#!/bin/bash

for f in *.inp; do
sed -i 's/[^a-zA-Z][gG][rR][iI][dD][0-9]//g' $f
sed -i 's/[^a-zA-Z][gG][rR][iI][dD][xX][0-9]//g' $f
sed -i 's/[^a-zA-Z][fF][iI][nN][aA][lL][gG][rR][iI][dD][0-9]//g' $f
sed -i 's/[^a-zA-Z][fF][iI][nN][aA][lL][gG][rR][iI][dD][xX][0-9]//g' $f
sed -i 's/[^a-zA-Z][nN][oO][fF][iI][nN][aA][lL][gG][rR][iI][dD]//g' $f
sed -i 's/[^a-zA-Z][nN][oO][fF][iI][nN][aA][lL][gG][rR][iI][dD][xX]//g' $f
done
```

---

## 5. 脚本使用步骤

1. 将脚本代码保存为扩展名为 `.sh` 的文件，该文件需与 `.inp` 输入文件位于同一目录下。
2. 使用 `chmod` 命令赋予该 `.sh` 文件执行权限。
3. 运行该 `.sh` 文件。

---

## 6. 脚本运行环境与范围

该脚本仅适用于 Linux 及类 Linux 环境（如 WSL）。脚本会扫描并修改当前目录下所有的 `.inp` 文件，删除其中包含的 Grid、GridX、FinalGrid、FinalGridX、NoFinalGrid、NoFinalGridX 关键字。

---

## 7. 脚本目标文件的限定

如果只需修改特定文件，可将脚本中的 `*.inp` 替换为具体的文件名。未匹配到目标扩展名的文件不会受到脚本影响，手动修改可能更安全。

---

## 8. %method 块内的关键字处理

该脚本无法删除位于 `%method` 块内部的相关关键字。用户需手动检查并处理 `%method` 块中的网格设置。

---

## 9. 脚本对注释内容的影响

使用该脚本可能会影响注释的可读性。若注释中包含这些关键字（例如 `# grid4 is too small`），脚本运行后可能仅保留注释文本的其余部分（如变为 `# is too small`），导致原意丢失。

---

## 10. ORCA 5.0 的网格精度关键字

ORCA 5.0 指定网格精度的关键字为 `defgrid1`、`defgrid2` 和 `defgrid3`。系统默认使用 `defgrid2`。`defgrid2` 的精度高于 ORCA 4 的默认设置，但计算耗时增加不多。除非确实遇到 `defgrid2` 精度不足的问题，否则无需额外指定 `defgrid3`。

---

## 11. ORCA 5.0 关键字兼容性反馈

目前仅已知上述网格相关关键字在 ORCA 4 支持而在 ORCA 5.0 中不再支持。若发现 ORCA 4 的其他关键字在 ORCA 5.0 中无法使用，建议及时反馈，以便更新脚本内容。
