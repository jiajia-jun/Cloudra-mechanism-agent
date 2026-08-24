# MLP 金标准选型调研总结（零 DFT 预算方案）

> **⚠ 已过时（2026-08-25 更新）**：本文"AIMNet2 主选 + MACE-OFF23 备选"的结论已被项目组决策推翻——
> 金标准计算引擎锁定 **MACE-OMol25 单引擎**（xTB 仅作预松弛/采样辅助），不引入 AIMNet2 或其他交叉验证器。
> 本文档保留供溯源，其中 AIMNet2 相关选型论证与容差推导不再适用。

> 日期：2026-08-25。目的：为四级机理基准测试集指定**单一机器学习势作为金标准能量方法**，
> 并给出其舒适区判据（元素/电荷/自旋/尺寸边界），支撑"仅在舒适区内选测试反应"的设计决策。
> 证据来源：`reaction_eval/`（第三方能垒评测 10 条）、`bench_sets/`（基准集定义 8 条）、
> `implementations/`（工程落地 8 条）、`models/`（8 篇模型原文 PDF，元数据未完成）。

## 一、核心结论（一句话版）

**可行，但必须放弃"MLP≈化学精度"的幻想，改为"在已知误差档位内设计容差"**：
通用开源 MLP 在训练域内的近平衡热化学可达 0.3–1 kcal/mol，扭转/构象能差 0.25–0.5 kcal/mol，
但"真反应势垒"的广谱成绩只有 ≈2–8 kcal/mol（视模型与子域）；出域即跳升到 4–14 kcal/mol 或直接失败。
因此：Easy/Normal 档考热化学与近垒反应（容差 ±1–3），Hard 档考真势垒（容差 ±5–8），
Impossible 档 = 出舒适区（金属、开壳、强多参考）——四档难度分级恰好获得物理依据。

## 二、方法 × 精度 × 域 × 成本对比（关键数字均有出处）

| 方法 | 势垒/反应精度（公开数字） | 舒适区 | 许可/获取 | 工程可用性 |
|---|---|---|---|---|
| **AIMNet2**(-wb97m-d3/-rxn) Chem Sci 2025 | GMTKN55 势垒类 WTMAD2 ≈8（≈其训练参考 B97-3c 自身 8.2）；**-rxn 变体势垒 RMSD ~2、IRC 剖面 ~1**；构象搜索成功 77%（vs GFN2-xTB 45.2%） | 14 元素 {H,B,C,N,O,F,Si,P,S,Cl,As,Se,Br,I}；wb97m 族支持中性+带电；-rxn 仅 HCNO 且强制闭壳层中性 | **代码+权重全 MIT**，HF 自动下载 | ASE 计算器 + geomeTRIC 全流程；唯一有 CPU 单核实测（略快于 GFN2-xTB） |
| **MACE-OFF23** JACS 2025 | 双芳基扭转垒 MAE 0.3–0.5 kcal/mol（DFT 自身 vs CCSD(T) 为 0.2）；TorsionNet500 ≈0.25；分子晶体升华焓 1.8 | **仅 10 元素 HCNOFPSClBrI、仅中性闭壳层** | 代码 MIT；**权重 ASL 学术许可**（不可商用再分发） | `mace_off()` ASE 计算器；小模型正常模偏差有负面报告 |
| **UMA / OMol25 系** arXiv 2025 | OMol25 训练模型有机 TS 搜索成功率 96.6%、每反应 <4 次 DFT 梯度（Marks 2026）；OOD 分子 SOTA | 83 元素、变电荷/自旋、≤350 原子 | fairchem 代码 MIT；**权重 FAIR Chemistry v1 明文不对中国大陆发放 + 实名门控** | `FAIRChemCalculator`；FD-Hessian 有曲率失真实证（乙烷案例虚频 3969i cm⁻¹ 假象） |
| MACE-OMol25 | 同上（OMol25 数据训练） | 同 UMA-omol | 权重 ASL | 同上 |
| AIQM1 Nat Commun 2021 | 能量 MAD 0.8 kcal/mol vs CCSD(T)*；生成热 CHNO 0.9 | 中性闭壳层 HCNO；带电物种 PA/G21EA 误差 8–14 | 开源（Δ-NN+ODM2*+D4 拼装） | SQM 级速度 |
| ANI-2x / TorchANI | TorsionNet500 MAE 1.30 | CHNOFClS 中性为主 | MIT | 官方明示非 GPU 性能降级；ANI-1x 在七模型横评中最差（11.07，逊于 xTB） |
| DeePEST-OS Nat Commun 2026 | DORTS-1K 势垒 MAE 0.60（纯 MACE 0.93；PaiNN 5.28；xTB 10.00） | 十主族元素；OOD(T1x) 3.80 | 研究代码 | MACE+xTB Δ-learning，TS 提速 4 个量级 |

**关键反例（必须记住）**：Zhao et al. Adv Sci 2025 七模型横评——所有预训练基础模型
（含 MACE-OFF23、Orb-v2 等）**不经微调无一能在反应 PES 上胜过 GFN2-xTB 定位 TS**。
→ 结论不是"MLP 不行"，而是"**选对模型家族 + 限定在其训练域内做经典 TS 流程**"才行。

## 三、指定 MLP 推荐

### 主选：AIMNet2（aimnet2-wb97m-d3 全族；反应题优先用 -rxn 校验）

理由（按权重排序）：
1. **许可最干净**：代码与全部权重 MIT，无门控、无地域条款（UMA 直接排除：FAIR Chemistry License 明文不对中国大陆发放）；
2. **唯一在正文公布 GMTKN55 成绩的开源通用 MLP**，势垒类精度已知且可解释（≈其训练参考级 B97-3c）；
3. 支持带电物种——含离子中间体/质子转移的反应可测（MACE-OFF23 做不到）；
4. 唯一有 CPU 单核公开实测（优化全程比 GFN2-xTB 还快一点），WSL 无 GPU 环境可跑；
5. -rxn 变体专攻反应：势垒 RMSD ~2、IRC 剖面 ~1 kcal/mol，正好覆盖基准核心题型。

### 备选：MACE-OFF23（L 模型）
纯中性闭壳层有机反应且需要更高扭转/构象精度时用；ASL 学术许可对本项目（学术基准）可用。
建议作为**第二意见交叉验证器**：主选与备选在同一批题目上的势垒差 >3 kcal/mol 的题目应人工复核。

### 排除：UMA/OMol25 系（许可地域条款）、ANI 系（域窄、无带电、横评垫底）、NequIP 等（需逐任务特训）。

## 四、金标准舒适区判据模板（写进基准规范）

| 维度 | 判据 | 依据 |
|---|---|---|
| 元素 | ⊆ {H,B,C,N,O,F,Si,P,S,Cl,Br,I}（-rxn 题限 HCNO） | AIMNet2 训练域 [Chem Sci 2025] |
| 电荷 | 总电荷 \|Q\|≤1 优先；两性离子中间体允许 | wb97m 族训练覆盖 \|Q\|≤2 |
| 自旋 | 仅闭壳层单重态；开壳自由基归 Hard（若换装 NSE 版）/ Impossible | AIMNet2-NSE Angew 2026："多数 MLIP 不区分自旋态" |
| 尺寸 | ≤50 重原子舒适区（SPICE 域）；数值 Hessian = 6N+1 次力调用，N=70 约 420 次 | SPICE 定义 + ASE vibrations 实现 |
| 键型 | 无金属、无强多参考（双自由基/反芳香过渡态谨慎） | UMA-M 也需 DFT 终验 [Marks 2026] |
| 相态 | 气相单分子/双分子反应；凝聚相反应不测（训练域以分子为主） | ANI-1xnr 教训：真空气相断键是另一族模型的坑 |
| 应用域距离 | 若引入嵌入空间最近邻判据：距离 >0.7 对应能垒 MAE 超 1 kcal/mol，应弃题 | DeePEST-OS Fig 5/7 |

## 五、对四级难度分档的直接映射

- **Easy（30 题）**：闭壳层中性、≤7 重原子可放大到 ≤20、单一明确通道（如周环、简单 SN2、缩合脱水）。
  容差设定依据：构象/扭转级精度 0.25–1 kcal/mol。
- **Normal（30 题）**：多步机理、离子中间体（AIMNet2 带电能力）、普通杂环；容差 ±3（对应通用域内势垒 ~2 kcal/mol 档）。
- **Hard（20 题）**：真势垒敏感反应、开壳（NSE 版）、曲率敏感鞍点；容差 ±5–8（GMTKN55 势垒类锚点）；
  必须加"虚频个数 + 虚频方向"硬闸门（MLIP FD-Hessian 曲率失真是已证实失效模式）。
- **Impossible（20 题）**：金属催化、强多参考、出元素域、FD-Hessian 稳定失败的简并鞍点体系。

## 六、遗留风险与对策

1. **预训练模型直接找 TS 会失败**（七模型横评）→ 基准流程固定为：xTB/CREST 采样预筛 → AIMNet2 opt → geomeTRIC TS 优化（以 xTB TS 为初猜）→ freq 验证 → IRC。评分考察流程编排正确性而非裸模型调用。
2. **Hessian 曲率失真** → freq 环节硬闸门；必要时用 autograd 解析 Hessian（须 `compile_model=False`）。
3. **容差即方法误差** → 评分规则中显式声明"容差 ≥ 金标准方法自身不确定度"，避免结构性零分（呼应 plan 第 164 行解耦原则）。
4. **models/ 子目录元数据未完成**（用户指示中止）：8 篇模型原文 PDF 已在手，后续如需逐条引用可补建 metadata.json。

## 七、引用勘误记录（检索中发现并核实）

- "GMTKN55 (Acc. Chem. Res. 2021)" 不存在 → 正典为 Goerigk et al., **PCCP 2017, 19, 32184**。
- BH9 非 Grimme 组工作 → 作者 Prasad, Pei, Edelmann, Otero-de-la-Roza, DiLabio，**JCTC 2021**。
- RDB7 正典出处为 **Grambow, Pattanaik & Green, Sci Data 7, 137 (2020)**（非 Nat Commun 2021）。
- ISO17 是 **129 个异构体**（非 17），共 645,000 样本。
- "RPC reaction path completion" 数据集未检获同名文献，可能为 T1x/RGD1/OA-ReactDiff 谱系内部称呼。
