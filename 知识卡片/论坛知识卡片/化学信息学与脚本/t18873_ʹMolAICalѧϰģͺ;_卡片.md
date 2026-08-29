---
key: t18873
title: ʹ��MolAICal�����ѧϰģ�ͺ;����㷨�������GCGR�Ĵ�ͷҩ�����
url: http://bbs.keinsci.com/thread-18873-1-1.html
domain: 化学信息学与脚本
source: keinsci
year: 2020
cards: 15
---

# ʹ��MolAICal�����ѧϰģ�ͺ;����㷨�������GCGR�Ĵ�ͷҩ����� — 知识卡片

## 1. MolAICal GCGR从头药物设计教程概述

该教程展示了使用MolAICal软件结合人工智能模型和经典算法进行胰高血糖素受体（GCGR）从头药物设计的过程。教程涵盖了从GCGR复合物结构处理、配体提取、结合盒定义到生成新分子的完整标准流程。MolAICal支持基于AI模型或经典片段库的方法生成位于GCGR结合口袋的候选药物分子。相关资源和文档可在MolAICal官方网站、博客及指定文献中获取。

---

## 2. 下载与准备教程文件

进行MolAICal的GCGR从头药物设计教程前，需下载MolAICal程序、UCSF Chimera结构可视化工具以及教程示例文件。教程示例文件存放于GitHub仓库的tutorials/master/001-AIGrow目录下。相关资源链接包括MolAICal主页、中文教程、Blogspot以及介绍软件功能的文献DOI。

---

## 3. 使用UCSF Chimera处理受体结构

处理胰高血糖素受体（GCGR）结构首先需下载PDB ID为5EE7的文件，并使用UCSF Chimera打开。用户应通过Select菜单选择并删除OLA、HOH、PE5、TLA等不需要的残基和分子，以获得纯净的受体结构。若后续使用AMBER力场，需在删除原始氢原子后重新加氢；若GCGR结构中已无原始氢原子，此步骤可省略。

---

## 4. 保存受体与制备无配体结构

在清理完不需要的原子后，需将包含氢原子的受体结构保存为PDB格式文件，命名为GCGRH.pdb。随后需选中并删除配体分子5MV，将剩余的纯受体结构另存为GCGRNoLigand.pdb文件。这两个文件分别用于后续的分子生成和结合口袋定义等步骤。

---

## 5. 提取与处理配体分子

提取配体分子时，需在UCSF Chimera中打开GCGRH.pdb文件并选中配体5MV。使用Invert (selected models)功能反转选中模型，并删除未选中的部分，从而仅保留配体分子。将处理后的配体分子保存为ligand.pdb文件，该文件将作为药物分子生成的起始点参考。

---

## 6. 测量结合位点中心坐标

定义结合盒需要确定口袋的中心坐标，需关闭当前会话并重新打开GCGRH.pdb，选中配体分子。通过Tools菜单下的Structure Analysis-->Distance工具，选择Axes/Planes/Centroids并定义中心点，即可获取配体的几何中心坐标。本教程中获取的中心坐标数值为x, y, z: -30.011, 1.665, -36.581。

---

## 7. 使用MolAICal生成并可视化结合盒

获取口袋中心坐标后，可使用MolAICal的box工具生成长宽高均为30.0埃的立方体结合盒描述文件box.bild。生成命令需指定中心坐标和长度参数，例如`molaical.exe -tool box -i "-30.011 1.665 -36.581" -l "30.0 30.0 30.0" -o "D:\workdir\MolAICal\tutorial\GCGR\box.bild"`。生成的box.bild文件可在UCSF Chimera中打开，以验证结合盒位置和大小是否覆盖受体结合区域。

---

## 8. 从配体结构获取初始片段

方法一通过从GCGR结合口袋中的已知配体结构直接截取片段作为初始生长点。在UCSF Chimera中打开ligand.pdb，利用Ctrl+鼠标或Ctrl+Shift+鼠标选择配体内部的一个或多个原子作为核心骨架。使用Invert (selected models)反转选择并删除非选中部分，然后对保留的初始片段加氢，并保存为sybyl Mol2格式文件startFrag.mol2。

---

## 9. 使用SMILES定义初始片段

方法二适用于结合口袋中没有已知配体结构的情况，用户需根据口袋特征选择一个关键氨基酸上的原子作为起始锚点，并使用SMILES字符串定义初始片段。配置文件中需将growMethod设为randomFrag，并通过startAtomPosition和startSmiFrag参数分别指定锚点原子位置文件和SMILES字符串。MolAICal能够自动将SMILES格式的片段放置到GCGR口袋中的指定位置。

---

## 10. 使用AI模型进行药物分子生成

选择使用AI模型生成药物分子时，需将配置文件中的libStyle参数设置为AIFrag。在Linux或Windows系统的后台目录中执行`molaical.exe -denovo grow -i InputParFileAI.dat`命令即可启动生成任务。若输出显示Warning信息提示原子与蛋白重叠，建议使用MD模拟工具或UCSF Chimera进行最小化能量或复合物优化。

---

## 11. 使用经典片段库进行药物分子生成

选择使用经典片段库生成药物分子时，需将配置文件中的libStyle参数设置为mol2，以调用用户自定义的片段库。执行命令为`molaical.exe -denovo grow -i InputParFileCP.dat`，软件可根据配置的coreNum参数调用多核CPU加速计算。处理原子重叠警告的方法与AI模型方法相同，需借助分子动力学或结构优化工具解决。

---

## 12. 查看与分析生成结果

计算完成后，结果文件保存在results目录中，本教程设置循环次数为30，使用30个CPU耗时约1-2小时。主要输出文件AstatisticsFile.dat包含生成分子的ID、名称、聚类信息、亲和力、分子式、InChIKey以及合成可及性等详细数据。用户可依据这些指标筛选和评估设计出的候选药物分子。

---

## 13. 药物分子生成的 k-means 聚类筛选方法

Affinity 展示了结合亲和力数值，Cluster 代表通过 k-means 聚类算法将构象分组，写入数据库用于后续筛选。
- Synthetic_Accessibility 数值范围为 0 至 100，其中数值 100 表示分子没有不可合成部分，代表极易合成。
- 该方法应用于药物分子生成研究。

---

## 14. MolAICal 生成的药物分子结构文件

在 UCSF Chimera 中打开 `GCGRNoLigand.pdb`、`ligand.mol2` 和 `lig_2.mol2` 文件。
- `lig_2.mol2` 文件中的红色小球是使用 MolAICal 程序基于 GCGR 原始蛋白结构生成的小分子。
- 此过程展示了药物分子生成的结果。

---

## 15. 冗余原子的处理与分子对接建议

蛋白结构中可能存在多余的原子或坐标，这可能与用于训练机器学习模型的参数不兼容。
- 建议使用 UCSF Chimera 删除多余的原子，然后重新进行计算。
- 为了更准确地评估生成的小分子与 GCGR 蛋白的结合情况，推荐使用分子力学/广义玻恩表面积模型（MM/GBSA）进行计算。
