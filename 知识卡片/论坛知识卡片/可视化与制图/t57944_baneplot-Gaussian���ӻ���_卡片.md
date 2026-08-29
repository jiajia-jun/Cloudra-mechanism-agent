---
key: t57944
title: baneplot-Gaussian���ӻ���ع���-���޸��޷���������
url: http://bbs.keinsci.com/thread-57944-1-1.html
domain: 可视化与制图
source: keinsci
year: 2026
cards: 18
---

# baneplot-Gaussian���ӻ���ع���-���޸��޷��������� — 知识卡片

## 1. 工具简介：baneplot

baneplot 是一个基于 gnuplot 的后处理绘图工具，用于生成 Gaussian 输出文件的监控与回归分析图表。该工具支持计算几何优化、势能面扫描、IRC 路径的监控，并能够自动调用 gnuplot 进行绘图。若当前目录下仅有一个 log 文件，程序会自动选择该文件进行处理。

---

## 2. 软件依赖与版本要求

使用 baneplot 需要安装 gnuplot，推荐使用的版本为 5.4.4。某些旧版本的 gnuplot 可能存在字符乱码问题，若绘图出现乱码建议更新 gnuplot 版本。

---

## 3. 命令用法与基本参数

baneplot 的基本调用格式为 `baneplot <gaussian_output.log> [选项]`。该工具支持自动识别当前目录下唯一的 log 文件。通过附加不同的命令行选项，可以指定绘图类型和数据来源。

---

## 4. 选项：优化收敛监控

使用 `--converge` 或 `-cv` 选项可以绘制几何优化收敛图。默认情况下，该选项会自动根据输出文件内容绘制 SCF 或 TD-DFT 能量变化。输出图片默认为 png 格式，适合在 VScode 等编辑器中查看。

---

## 5. 选项：指定收敛数据类型

为了特定类型计算，可使用 `--converge-td` (或 `-cv td`) 强制绘制 TD-DFT 收敛图，或使用 `--converge-sp` (或 `-cv sp`) 强制绘制仅含 SCF 部分的收敛图。对于 ONIOM 计算，需使用 `--converge-oniom` (或 `-cv oniom`) 选项来正确提取 ONIOM 能量数据进行绘图。

---

## 6. 选项：势能面扫描绘图

使用 `--scan` 或 `-sc` 选项可绘制势能面扫描图。默认设置下，程序会自动检测并在图中分别绘制 SCF 和 TD-DFT 数据曲线，或者在纯 SCF 计算中仅绘制单条曲线。

---

## 7. 选项：IRC 路径绘图

使用 `--irc` 或 `-i` 选项可以绘制 IRC 路径图，该选项会自动提取 IRC 计算结果中的能量变化。对于含 TD-DFT 的计算，程序会自动处理并绘制相关数据。

---

## 8. 选项：外部数据绘图

使用 `--data` 或 `-d <data_file>` 选项可以直接从指定的文本数据文件进行绘图。数据文件第一行应为表头，以 "index" 开头，后跟 Y 轴标签，后续行依次为索引和数值。例如：`banedata -a -sc 49 8 > data.txt` 或 `banedata -a -e >> data.txt` 生成的文件。

---

## 9. 选项：双 Y 轴与单 Y 轴模式

当使用外部数据文件绘图时，若数据包含多列，baneplot 支持生成双 Y 轴图表。若需强制使用单 Y 轴模式，可配合使用 `--single` 或 `-s` 选项。

---

## 10. 选项：终端输出模式与文件保留

使用 `--dumb` 或 `-du` 选项可将输出模式设为 ASCII 字符终端模式，直接在 Shell 控制台中显示图形轮廓。使用 `--keep` 或 `-k` 选项可以在绘图完成后保留生成的临时数据和脚资料件。

---

## 11. 选项：帮助信息

使用 `--help` 或 `-h` 选项可以显示 baneplot 的完整使用帮助信息，包括所有可用的命令行参数及其说明。

---

## 12. 辅助工具：banedata

banedata 是一个与 baneplot 配合使用的辅助工具，用于从 log 文件中提取数据并写入数值文件。该工具支持读取 log 文件中的特定数值并导出，以便后续通过 `--data` 选项传递给 baneplot 进行快速绘图。

---

## 13. 工具功能更新记录

baneplot 在 2026-05-20 版本中增加了对读取 log 文件并写入数值文件的支持。在 2026-05-24 版本中，优化了绘图参数设置，提升了图形质量。

---

## 14. ORCA 输出文件的可视化流程

ORCA 输出的计算结果可以通过 OfakeG 工具转换为伪造的 Gaussian 输出文件，从而使用 baneplot 进行可视化。OfakeG 由原作者开发，baneplot 已针对该工具的输出格式进行了微调适配。

---

## 15. OfakeG 转换示例

使用 OfakeG 处理 ORCA 输出文件（如 `optTS_freq_ORCA6.0.0.out`）后，会在当前目录生成后缀为 `_fake.out` 的文件。生成的伪造文件包含了优化步骤和频率分析信息，可供 baneplot 读取并绘制收敛图。例如：`OfakeG optTS_freq_ORCA6.0.0.out` 后运行 `baneplot optTS_freq_ORCA6.0.0_fake.out -cv`。

---

## 16. OfakeG 的功能与版本

OfakeG 能够基于 ORCA 输出文件生成包含优化步骤和频率分析数据的伪 Gaussian 输出文件。文中使用的示例版本为 1.3.3（发布日期 2025-May-27），该版本经过调整以适配 baneplot 的读取需求。

---

## 17. 其他程序输出的支持

除了 ORCA，用户还可以参考 fakeg 相关工具，将 AMESP、BDF 等其他量子化学程序的输出转换为 baneplot 可识别的格式，从而实现对各类计算结果的优化监控可视化。

---

## 18. 联系方式与反馈

baneplot 的作者为 Bane Dysta。用户可通过电子邮件 banerxmd@gmail.com 或指定论坛反馈链接提供意见或报告 Bug。
