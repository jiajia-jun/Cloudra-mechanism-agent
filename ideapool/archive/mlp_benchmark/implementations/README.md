# implementations/ —— 候选 MLP 工程落地信息调研笔记

## 总述

本子任务面向四级反应机理基准测试集的"单一指定 MLP 金标准能量方法"决策，调查了四个候选机器学习势家族的**工程落地信息**：TorchANI（GitHub）、MACE/mace-torch（pip）、AIMNet2（HuggingFace checkpoint）与 Meta UMA/fairchem（HuggingFace 门控 checkpoint），外加共用流程底座 geomeTRIC 和一份直接的 TS 搜索实证基准。共整理 **8 个元数据条目、4 个开放获取全文 PDF**。核心结论：(1) 四个候选都能通过 ASE calculator 接入 geomeTRIC 的 opt→freq→TS→IRC 全流程（geomeTRIC 文档明确支持 TS 优化、NEB、IRC、振动分析并提供 ASE Engine）；(2) 许可证方面 AIMNet2 checkpoint 为 MIT、TorchANI 与 mace-torch 代码为 MIT，但 MACE-OFF23/MACE-OMOL 等**模型权重是 Academic Software License（学术用途友好、商用受限）**，UMA 权重为 FAIR Chemistry License v1（允许商业与非商业使用，但**不对中国等地区发放**且需实名门控申请）；(3) CPU 上 ≤50 重原子的公开实测数字极少——最硬的一条实测是 AIMNet2 论文：i7-9700K 单核几何优化全程耗时比其 L40S GPU 实现慢约两个数量级但仍略快于 GFN2-xTB；其余速度数字均为 GPU 锚点（UMA 论文 Table 1/3 给出 100 原子体系各模型 21–89 steps/s）。数值 Hessian 按 ASE 默认中心差分需 6N+1 次力调用，70 原子体系约 420 次，用已测 GPU 调用时间外推为秒级（详见下文公式）。

## 一、对比表：方法 × 发布渠道 × 许可 × 适用域 × 成本

| 维度 | TorchANI (ANI1x/2x) | MACE-OFF23 (经 mace-torch) | AIMNet2 (-wb97m-d3 / -rxn) | UMA (fairchem) |
|---|---|---|---|---|
| **发布渠道** | `pip install torchani`（PyPI，v2.x）；权重随包分发 | `pip install mace-torch`≥0.3.6，`mace_off()` 自动下载缓存至 `~/.cache/mace` [PyPI] | HF `isayevlab/aimnet2-*`，`pip install "aimnet[hf]"` 自动下载 [HF 卡片] | HF `facebook/UMA` **门控**：实名+生日+机构申请，`huggingface-cli login` 后 `get_predict_unit("uma-s-1p2")` [HF 页面] |
| **代码 License** | MIT [repo 徽章] | MIT [PyPI] | aimnet 包开源（github.com/isayevlab/aimnetcentral）[Chem Sci 论文 Code availability] | MIT（fairchem-core）[README] |
| **模型权重 License** | MIT（模型在代码仓库内）[repo] | **ASL 学术许可**（OFF23/OMAT/OMOL/MH 均 ASL；仅 MACE-MP-0 系列为 MIT）[PyPI 表格] | **MIT**（全部 5 个 checkpoint 仓库标签 'License: mit'）[HF] | **FAIR Chemistry License v1**：允许商业与非商业，但 "available ... except ... in China, Russia, and Belarus"（逐字）[HF] |
| **元素域** | ANI 系经典 CHNOFClS 域（论文谱系） | H,C,N,O,F,P,S,Cl,Br,I 十元素 [arXiv 正文] | wb97m-d3 族 14 元素 {H,B,C,N,O,F,Si,P,S,Cl,As,Se,Br,I}；**-rxn 仅 H,C,N,O** [Chem Sci/HF 卡片] | 83+ 元素（OMol25 训练集覆盖）[OMol25 arXiv] |
| **电荷/自旋** | 中性分子为主（ANI 架构限制） | 仅中性闭壳层 [arXiv 正文] | wb97m-d3 支持中性+带电（训练覆盖 \|Q\|≤2 至 9）；**-rxn 强制净电荷=0、仅闭壳层**（calculator 直接 raise）[Chem Sci/HF 卡片] | omol 任务显式支持非中性 charge/spin，README 有 CH2 单三重态自旋隙示例 [fairchem README] |
| **精度锚点（kcal/mol 级）** | TorsionNet500 MAE：ANI-2x 1.30（被 AIMNet2 论文引用作对比基线） | 扭转扫描、分子晶体、液体性质系统验证通过（wB97M+D3/SPICE 训练）[arXiv] | AIMNet2: TorsionNet500 MAE 0.32、构象搜索成功率 77%（≈B97-3c 的 75%）；**-rxn: 势垒 RMSD ~2、IRC 剖面 ~1** [Chem Sci/HF 卡片] | OMol25 OOD 分子测试 SOTA 级；TS 搜索实证见下 [arXiv] |
| **≤50 重原子单点/步进速度（实测来源）** | **未找到公开实测毫秒值**；README 逐字："If you don't run TorchANI on a GPU, expect degraded performance." | A100/OpenMM ~600 原子盒子：S 24 steps/s、M ~13、L ~3.2 [arXiv Sec III E]；H100/100 原子：OFF23-L 89 steps/s [UMA 论文 Table 3] | CPU i7-9700K 单核全程优化比 L40S GPU **慢约两个数量级**、仍略快于 GFN2-xTB；GPU ≤80 原子比 GFN-FF 快 ~5×（无逐次毫秒表）[Chem Sci Fig. 6 讨论] | H100/100 原子 steps/s：uma-s 44、uma-s-1p2 53、uma-m 21 [UMA 论文 Table 3]；1k 原子 16/24/3 inf/s [Table 1] |
| **opt/freq/TS/IRC 全流程** | ✅ `model.ase()` ASE 计算器（energy/free_energy/forces/stress）+ geomeTRIC | ✅ `mace_off()`/`mace_mp()` ASE 计算器 + geomeTRIC | ✅ `AIMNet2ASE` + geomeTRIC；**Hessian 必须 `compile_model=False`**（torch.compile 在 GELU 双反传挂起）[HF 卡片] | ✅ `FAIRChemCalculator` + geomeTRIC（README 自带 LBFGS/FIRE 示例） |

> 表中所有数字的出处标注见方括号，完整链接见文末引用。

## 二、全流程可行性（opt + freq + TS + IRC）

geomeTRIC 是四个候选共用的流程底座，文档首页功能清单明确列出：Energy minimization、Constrained energy minimization、**Transition state optimization**、**Nudged elastic band**、Conical intersection optimization；目录树另含 **Intrinsic reaction coordinate** 与 **Hessian calculations & vibrational analysis** 两章；Engines 列表含 **ASE Engine**（pip/conda 安装，BSD-3-Clause）。因此"MLP 作 ASE calculator + geomeTRIC 做 TS 优化与 IRC"不需要任何 DFT 即可闭环。

实证支撑（Marks et al., arXiv:2604.00405）：在 Baker 24 反应 + Sharada 9 反应上，FSM 平均成功率 **88.9%**（native 90.3%，平均 9.9 次梯度评估/成功搜索）；Sharada 集含 alanine dipeptide、Diels–Alder、Ireland–Claisen 等 **20–50+ 原子**体系仍达 89.8%。OMol25 训练的模型表现最好：**MACE-OMol25 有机体系成功率 96.6%、每反应 <4 次 DFT 梯度评估**。

**频率校验环节的风险提示（重要）**：
- Marks et al. 报告 MLIP 有限差分 Hessian 存在系统性曲率失真：ethane dehydrogenation 案例中 UMA-M 的 FD-Hessian 虚频 3969i/949i/762i cm⁻¹ vs DFT 2343i/843i/598i cm⁻¹，直接导致收敛到错误鞍点；
- Ranasinghe et al.（arXiv:2503.11537，JCIM 2025）摘要逐字："A normal mode analysis of 14 simple benchmark molecules revealed that the small MACE-OFF23 model shows large deviations from the reference quantum-mechanical energy surface."
- 结论：基准集设计应把"虚频个数与模式方向校验"作为硬闸门，且难度分层时把 TS 曲率敏感反应（简并鞍点、二级鞍点竞争）归入 Hard/Impossible 档。

## 三、数值 Hessian 成本估计

依据 ASE 源码（ase/vibrations/vibrations.py）：默认 `delta=0.01 Å`、`nfree=2`，docstring 逐字 "This will calculate the forces for 6 displacements per atom +/-x, +/-y, +/-z"。即：

```
数值 Hessian 成本 = (6 × N_vib + 1) 次力调用
≤50 重原子 + ~20 H → N≈70 → 约 421 次力调用
```

用 UMA 论文 Table 3（H100，100 原子）实测 steps/s 外推（**推断值，非实测**）：
- MACE-OFF23-L：89 steps/s → ~11 ms/次 → Hessian ≈ **4.7 s**
- uma-s-1p2：53 → ~19 ms → ≈ **8 s**；uma-s：44 → ~23 ms → ≈ **9.5 s**；uma-m：21 → ~48 ms → ≈ **20 s**

CPU 场景：AIMNet2 论文唯一给出 CPU 实测口径（单核 i7-9700K 全程优化比 GPU 慢约两个数量级），据此推断 CPU 上单次调用在几十至上百毫秒量级、70 原子数值 Hessian 在**分钟级**；AIMNet2-rxn 卡片另指出 autograd 解析 Hessian 可用但须关闭 torch.compile。TorchANI 无公开实测值，仅有官方"GPU 之外性能降级"定性声明。

## 四、对本项目的落地建议（供 Coordinator 决策参考）

1. **合规红线**：若指定 UMA 必须先解决 HF 门控与地域条款问题（明确排除中国大陆）；MACE-OFF23/MACE-OMOL 权重为 ASL，学术基准发布可用但不可商用再分发权重；AIMNet2(MIT)+MACE-MP(MIT) 是许可最干净的组合。
2. **域匹配**：纯有机中性闭壳层反应 → MACE-OFF23 或 AIMNet2-wb97m-d3/rxn；涉及带电中间体 → AIMNet2（14 元素+带电）或 UMA-omol（变自旋）；含 F/P/S/Cl/Br/I 的反应 → MACE-OFF23 或 AIMNet2（-rxn 不行，仅 HCNO）。
3. **成本预算**：以 GPU 锚点计，单个 ≤70 原子反应做 opt(~50 步)+freq(~420 次)+TS+IRC(~200 步) 合计量级约数百至上千次调用 ≈ 数十秒（GPU）/ 分钟级（CPU），52 篇文献池 124 个候选反应的全量筛选完全可行。
4. **xTB 分工不变**：本调研确认 xTB 只承担采样/预筛（AIMNet2 论文中 xTB 优化质量显著劣于 AIMNet2：构象搜索成功率 45.2% vs 77%），最终能量数字一律由指定 MLP 出具。

## 五、引用（标题 + DOI/URL）

1. TorchANI GitHub 仓库（MIT；ASE 计算器源码 torchani/ase.py）— https://github.com/aiqm/torchani
2. Pickering, Xue, Huddleston, Terrel, Roitberg. *TorchANI 2.0: An Extensible, High-Performance Library for the Design, Training, and Use of NN-IPs*. JCIM 65(21), 11656–11671 (2025). https://doi.org/10.1021/acs.jcim.5c01853
3. mace-torch · PyPI（v0.3.16，License 表）— https://pypi.org/project/mace-torch/
4. Kovács et al. *MACE-OFF: Transferable Short Range Machine Learning Force Fields for Organic Molecules*. arXiv:2312.15211；期刊版 JACS (2025). https://doi.org/10.1021/jacs.4c07099 ；PDF: 2023_kovacs_maceoff23.pdf
5. Anstine, Zubatyuk, Isayev. *AIMNet2: a neural network potential to meet your neutral, charged, organic, and elemental-organic needs*. Chem. Sci. 16(23), 10228–10244 (2025). https://doi.org/10.1039/D4SC08572H ；PDF: 2025_anstine_aimnet2.pdf
6. Isayev Lab. *AIMNet2-rxn* HF 模型卡（MIT；同族 aimnet2-wb97m-d3/-nse/-pd/-2025）— https://huggingface.co/isayevlab/aimnet2-rxn
7. Wood et al. *UMA: A Family of Universal Models for Atoms*. arXiv:2506.23971；checkpoint: https://huggingface.co/facebook/UMA ；代码: https://github.com/facebookresearch/fairchem ；PDF: 2025_wood_uma.pdf
8. Levine et al. *The Open Molecules 2025 (OMol25) Dataset, Evaluations, and Models*. arXiv:2505.08762 — https://arxiv.org/abs/2505.08762 （UMA 舒适区背景：83 元素、变电荷/自旋、≤350 原子）
9. Wang, Song. *Geometry optimization made simple using translation and rotation coordinates* (geomeTRIC). JCP 144, 214108 (2016). https://doi.org/10.1063/1.4952956 ；文档 https://geometric.readthedocs.io/ ；NEB 配套: Park, Pritchard, Wang. JCTC 21, 12048 (2025). https://doi.org/10.1021/acs.jctc.5c01540
10. Marks, Vandezande, Gomes. *Reliable and Efficient Automated Transition-State Searches with Machine-Learned Interatomic Potentials*. arXiv:2604.00405 — https://arxiv.org/abs/2604.00405 ；PDF: 2026_marks_mlip_tssearch.pdf
11. ASE Vibrations 数值 Hessian 实现（delta=0.01 Å, nfree=2, 6N 次位移）— https://gitlab.com/ASE/ase/-/raw/master/ase/vibrations/vibrations.py
12. Ranasinghe et al. *Basic stability tests of machine learning potentials for molecular simulations in computational drug discovery*. JCIM 65(17), 8980–8999 (2025). https://doi.org/10.1021/acs.jcim.5c01150 ; arXiv:2503.11537（MACE-OFF23 小模型正常模偏差警告）
