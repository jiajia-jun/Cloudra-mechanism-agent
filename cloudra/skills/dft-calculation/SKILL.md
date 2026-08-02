---
name: dft-calculation
description: Provide domain expertise for DFT (Density Functional Theory) quantum chemistry calculations on molecules and clusters using Gaussian/ORCA. Use when selecting functionals/basis sets, planning transition state workflows, and troubleshooting input errors. For periodic solids, see first-principles-calculation.
---

# 1. 本地工具链映射 (Toolchain Mapping)
在执行分子/团簇 DFT 计算时，动作应与 `CLOUDRA` 本地工具链紧密绑定：
- **获取分子结构与建模**：SMILES 是分子结构的核心。当缺乏现成的三维坐标文件时，优先调用本地 SMILES 相关工具：
  - 若用户只给出了一张化学结构图，优先调用 `image_to_smiles` 识别 SMILES。
  - 若需将 SMILES 转为 3D 坐标，调用 `smiles_to_mol` 并设置 `generate_3d=True`。
  - 若只需生成高斯输入文件，可直接在调用 `gjf_writer` 时设置 `source_type="smiles"`。
- **生成输入文件**：推荐调用 `gjf_writer` 生成 `.gjf`，减少手写格式错误。尽量避免在输入文件正文中写注释，以减少解析风险。
- **结构洞察与微调**：调用 `internal_coordinates` 作为你的“眼睛”和“双手”。当你需要像人类在 GaussView 中那样审视或修改分子骨架时，用它将笛卡尔坐标转换为 Z-matrix。你可以阅读 Z-matrix 和其附带的 `Anomalies` 异常键长报告来发现过渡态断键/成键位点；也可以通过直接修改 Z-matrix 文本中的键长、键角、二面角数值，再将其转回 xyz 坐标，实现结构的“手工拖拽”。
- **任务投递**：统一调用 `submit_compute_job`。长耗时任务建议设置 `is_async=True` 异步执行。
- **结果解析**：优先调用 `log_parser` 等工具提取能量、频率、收敛状态；避免直接用 `cat` 读取巨型日志。

# 2. 限制与例外 (Constraints & Exceptions)
以下规则是常见最佳实践，但存在合理例外。遇到矛盾时，优先以**具体体系、目标性质和最新文献**为准。

1. **输入文件注释**：Gaussian 官方文档允许用 `!` 添加注释，但实践中 `.gjf` 文件中的注释/空行常因版本或解析差异导致任务异常。因此建议不在计算指令区写注释，必要时把说明放在文件外部或标题行，并务必先用小体系测试。[Gaussian Input Format](https://gaussian.com/input/)
2. **HF (Hartree-Fock)**：对大多数定量计算，普通 HF 因缺少电子相关而不被推荐。但在以下情况仍有价值：
   - 作为 DFT/后自洽方法的参照计算；
   - 需要 HF 轨道作为多参考、EOM 或强自旋污染开壳层体系的初猜（如 Q-Chem 中可用 DFT 轨道替代 HF 轨道，反之 HF 轨道也可作为参考）；
   - 使用色散校正 HF（HFLD）专门分析非共价相互作用能。[HFLD paper](https://pmc.ncbi.nlm.nih.gov/articles/PMC9009084/)
3. **MP2**：普通 MP2 对弱相互作用和过渡金属常表现不佳，原则上不建议盲目使用。但 MP2.5、SCS-MP2 等变体在部分弱相互作用基准中仍可作为对照方法。
4. **M06-2X 与过渡金属**：M06-2X 主要针对主族热化学、动力学和非共价相互作用参数化，对含过渡金属（尤其是开壳层/强相关）体系风险较高，建议优先选用 M06、PBE0-D3(BJ)、TPSSh-D3(BJ) 等。若体系以轻金属或主族配位为主，且性质对交换相关能敏感，可酌情使用 M06-2X 并加基准验证。[M06 Suite](https://comp.chem.umn.edu/truhlar/docs/773fin_plus_supp_info.pdf)
5. **QST2 / QST3**：Gaussian 的 `Opt=QST2/QST3` 属于同步传递引导的过渡态初猜方法，对简单双分子反应、有清晰反应物和产物的体系仍可作为初猜工具，但复杂体系建议优先使用柔性扫描 + `Opt=(TS,noeigen,calcfc)`。注意 QST2/QST3 不应与 `TS` 关键词同时指定。[Gaussian QST2](https://gaussian.com/qst2/) [STQN Methods](https://www.cup.uni-muenchen.de/ch/compchem/geom/stqn.html)
6. **基组一致性**：IRC 和振动分析原则上应使用与几何优化相同的基组，以保证势能面一致；单点能计算完全可以用更大基组进行外推或能量修正。
7. **弥散函数**：
   - 计算极化率、偶极矩、Rydberg 态或阴离子时，通常需要弥散函数（如 `def2-TZVPD`、`aug-cc-pVDZ`）。
   - 键级分析、布居分析、NMR 计算通常避免使用弥散函数，因为弥散基函数会离域化并稀释局部分析结果；但如果研究对象本身是弥散态（如弱配位阴离子），仍需带弥散并谨慎解释。

# 3. 科学知识库：泛函与基组选型 (Scientific Knowledge Base)
在调用 `gjf_writer` 设定 `method` 和 `basis_set` 时，以本节内容为一般性事实依据；最终选择应结合体系特点和最新基准。

## 3.1 泛函选择指南
*   **一般精度顺序**：CCSD(T) > 双杂化泛函 > 恰当选用的普通泛函 > MP2 > HF > 半经验方法。
*   **高低搭配策略**：用普通泛函做结构优化和振动分析（如大体系用 `B3LYP-D3(BJ)`），再用双杂化泛函（如 `wB97M(2)` 或 `PWPB95-D3(BJ)`）算单点能。

| 计算任务/体系 | 首选/推荐泛函 | 备选或特定条件泛函 |
| :--- | :--- | :--- |
| **主族结构优化与振动** | `B3LYP-D3(BJ)` | 显著共轭体系用 `wB97XD` |
| **有机体系热力学** (反应能等) | `wB97M-V` | `M06-2X` |
| **各类弱相互作用** | `wB97M-V`, `wB97X-V` | `PW6B95-D3(BJ)`, `M06-2X` |
| **局部激发与一般激发态** | `PBE0` (结合 TDDFT) | `CAM-B3LYP`, `wB97XD` (大共轭/CT) |
| **极化率 /偶极矩等电性** | `PBE0`, `wB97M-V` | `BHandHLYP` (大共轭), `LC-wPBE` |
| **多参考特征强 /团簇** | `r2SCAN`, `TPSS` | `PBE0`, `MN15L` |
| **过渡金属 (闭壳层反应)** | `wB97X-V`, `wB97M-V` | `PBE0-D3(BJ)`, `TPSSh-D3(BJ)` |
| **过渡金属 (开壳层反应)** | `TPSS0-D4` | `PBE0-D4` |
| **NMR 化学位移** | `B3LYP` (结合标度法) | `revTPSS` (结合 pcSseg-1 基组) |

## 3.2 基组选择指南
理论方法对基组的依赖性存在根本差异，切勿混用评判标准。

*   **针对 DFT 的推荐（优先选 def2/pcseg 系列）**：
    *   **日常够用/优化**：`6-31G*`, `6-311G**`, `def-TZVP`
    *   **高精度/单点能**：`def2-TZVP`, `def2-TZVPP`, `pcseg-2`
*   **特定任务基组建议**：
    *   **弱相互作用能**：主导体系必须加弥散，如 `ma-def2-SVP` / `jun-cc-pVDZ`，建议加 BSSE 校正。
    *   **势垒计算**：有算力可加少量弥散（如 `ma-`），或提升 zeta 数。
    *   **相对论计算**：全电子相对论必须用专用基组（如 `cc-pVnZ-DK`）；第四周期及以后重元素强烈推荐赝势基组。

# 4. Agent 工作流：过渡态 (TS) 搜索 (Workflow State Machine)
当接收到“过渡态搜索”任务时，建议遵循以下程序化执行步骤：

**Step 1: 建模与精准初猜 (Modeling & Initial Guess)**
- 过渡态搜索对初猜严格。优先从网络或数据库获取核心分子的 SMILES，使用系统工具转换为坐标。
- **结构洞察与拖拽**：调用 `internal_coordinates` 工具作为你的“眼睛”。将坐标转为 Z-matrix，通过 `Anomalies` 检测敏锐捕捉处于 1.3~2.0 倍共价半径之间的可疑原子对（注意甄别普通的 1-3 相互作用）。像人类在 GaussView 中拖拉结构一样，你可以直接编辑 Z-matrix 文本，人为拉长反应物中将要断裂的键，缩短将要形成的键，然后用该工具将其转回笛卡尔坐标，从而手工捏出一个高质量的 TS 初猜。
- 基于分子结构对反应坐标进行柔性扫描。为节省算力，可先用半经验方法（如 xtb）扫描。**请注意，xtb在较大分子的过渡态面前的精度可能比较差，扫出了奇异的结果建议再使用优化级别扫一遍**
- 提取势能较高且梯度较小的点作为 TS 初猜。找到初猜后，建议先将结构展示给用户确认，再开启正式搜索。

**Step 2: 任务构建与投递 (Build & Submit)**
- 调用 `gjf_writer` 生成输入。
- **推荐关键词组合**：`opt=(ts,noeigen,calcfc)`。可视收敛情况调整，例如增加 `maxstep=10` 或 `int=ultrafine`。
- `opt` 和 `freq` 可连用，这是高斯标准做法；过渡态需要唯一虚频，建议带上 `freq` 验证。
- 调用 `submit_compute_job` 提交任务。无语法错误后，使用异步提交 (`is_async=True`)。

**Step 3: 计算单点能 (Single Point Energy)**
- 保持几何优化时的基组一致，去掉 `opt` 和 `freq` 关键词，提高泛函级别计算单点能。

**Step 4: 运行与验证 IRC (IRC Validation)**
- 计算级别建议与 TS 搜索一致，构建参数如 `irc=(lqa,calcfc,maxpoint=80)`。
- *逻辑验证*：作 IRC 曲线。如果曲线不平滑（有平台或噪声），说明过渡态精度不够或位置不对。但不必执着于整条irc曲线的完整性，只要两端能够优化到反应物和产物即可。
- *重搜策略*：此时不仅要加上 `maxstep=10`，还应该加上积分格点精度参数（如 `int=ultrafine` 或 `int=superfine`）重新计算 TS。

过渡态搜索任务一般伴随着机理寻找的任务，一般策略是：**以过渡态为中心，搜索并跑出irc后对两端进行优化得到中间体，以此找到完整的能垒**

# 5. 异常诊断与排障断路器 (Circuit Breakers)
如果 `submit_compute_job` 失败，或 `log_parser` 返回解析异常，请在重试前比对以下错误：

1. **色散冲突诊断**：检查当前泛函是否支持所选的色散校正（例如 M06-2X 不支持 GD3BJ）。
2. **结构奇异性排查**：如果报告 Hessian 矩阵无法计算，检查分子中是否存在明显的直线键角。如有，请改用笛卡尔坐标进行几何优化。
3. **IRC 步长发散**：若出现步长不收敛，直接将算法换用 `lqa`。
4. **IRC 异常终止**：若只跑了几步就 normal termination：
   - 过渡态不够平滑：需增加精度重算高精度 TS（见 Step 4 重搜策略）。
   - 反应能垒过平：尝试在 gjf_writer 中追加 `extra_keywords="IOp(1/108=-1)"` 取消收敛判断。
5. **freq数值崩溃**：有时freq突然崩溃并不是物理上的问题，在排查了无不合理距离等问题后，可以考虑读取已经算过的几何优化文件中的频率数据：geom=allcheck guess=read freq