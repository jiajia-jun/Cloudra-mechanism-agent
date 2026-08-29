---
key: t57134
title: ����Gaussian�ֽ����/����/����Ƕ������ܵĹ���
url: http://bbs.keinsci.com/thread-57134-1-1.html
domain: Gaussian使用
source: keinsci
year: 2025
cards: 15
---

# ����Gaussian�ֽ����/����/����Ƕ������ܵĹ��� — 知识卡片

## 1. Gaussian 输出简正模式贡献率

Gaussian 程序使用 `freq=intmode` 关键词可以打印出各个简正模式对重组能的贡献。该功能需要配合 `IOp(7/75=-1)` 使用。

---

## 2. Gaussian 输出 Huang-Rhys 因子

Gaussian 程序使用 `FCHT` 和 `print=huangrhys` 关键词可以打印各个振动模式对应的 Huang-Rhys 因子。这些因子结合简正模式信息可用于计算各个模式对重组能的贡献。

---

## 3. 重组能计算原理

重组能可以分解为各个振动模式的贡献之和，也可以分解为内坐标（键长、键角、二面角）的贡献。相关数学推导和理论背景已编写成 LaTeX 格式并发布在 GitHub 项目的 README 文件中。

---

## 4. Gaussian 输入文件设置

在 Gaussian 输入文件中，通过 `%oldchk=opt_Azulene.chk` 调用优化后的检查点文件。计算行使用 `#p geom=allcheck freq(readfc,fcht,readfcht,intmode) IOp(7/75=-1)` 设置，并配合 `initial=source=chk final=source=chk spectroscopy=onephotonemission print=(huangrhys,matrix=JK)` 指定初终态来源及打印选项。

---

## 5. 输入文件检查点文件顺序

Gaussian 输入文件末尾需要按顺序指定初态和终态的检查点文件名，例如 `td_Azulene.chk` 和 `opt_Azulene.chk`。计算发射光谱时，`initial` 和 `final` 的 chk 文件位置需要与实际物理过程对应正确。

---

## 6. 吸收光谱计算关键词

若计算吸收光谱而非发射光谱，需将关键词 `spectroscopy=onephotonemission` 修改为 `spectroscopy=onephotonabsorption`。同时需要相应调整初态和终态检查点文件的位置。

---

## 7. 收敛度错误信息

Gaussian 计算过程中可能出现 `ERROR: Low progression after class xxx. Total convergence = xxx%.` 的报错。只要程序能继续运行并输出 Huang-Rhys 因子，该错误通常可以忽略，不影响后续数据处理。

---

## 8. 文件读取错误

计算过程中出现 `FileIo operation on non-existent file.` 错误，通常是因为检查点文件路径放反或路径错误。应检查 `initial` 和 `final` 指定的 chk 文件顺序是否正确，并确认文件是否存在。

---

## 9. intmode 脚本处理数据

计算完成后，可使用 `intmode` 脚本处理 Gaussian 生成的 log 文件。命令格式为 `./intmode huang-rhys.log`，该命令将解析 log 文件并输出内坐标对重组能的详细贡献。

---

## 10. 脚本输出格式：键长贡献

脚本输出结果包含 `Internal Coordinate Contribution to Reorganization Energy` 部分。其中 `R (Bond Lengths/Angles/Dihedrals)` 列表详细展示了每个键长坐标（如 R12 R(6,7)）及其对重组能的百分比贡献。

---

## 11. 脚本输出格式：键角贡献

脚本输出结果中的 `A (Bond Lengths/Angles/Dihedrals)` 列表展示了每个键角坐标（如 A12 A(6,4,11)）及其对重组能的百分比贡献。

---

## 12. 脚本输出格式：二面角贡献

脚本输出结果中的 `D (Bond Lengths/Angles/Dihedrals)` 列表展示了每个二面角坐标（如 D19 D(11,4,6,7)）及其对重组能的百分比贡献。

---

## 13. 重组能贡献汇总

脚本输出的 `Summary: Total Contribution by Coordinate Type` 部分汇总了键长、键角和二面角三类内坐标对重组能的总贡献百分比。总和应接近 100%（例如显示 99.79%）。

---

## 14. 数据输出文件

脚本运行后会生成 `intmode.dat` 和 `lambda.dat` 两个文件。`intmode.dat` 保存了详细的内坐标贡献数据，`lambda.dat` 保存了重组能相关数据。

---

## 15. 可视化数据来源

`intmode.dat` 和 `lambda.dat` 中的数据可用于绘制可视化图表，以直观展示不同内坐标对重组能的贡献分布。
