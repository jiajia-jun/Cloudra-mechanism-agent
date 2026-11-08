# PDB / mmCIF 探测与选择性清洗

状态：已实现并完成本地真实后端验证。远端 CI 与合并状态以仓库 PR 为准；实现边界见末节。

## 1. 目标

提供两个工具：

- `pdb_inspect`：探测已有残基缺原子、内部缺残基、N/C 端缺段，返回候选结合水和金属周围可能配位的原子及依据。
- `pdb_clean`：Agent 根据研究目的选择清洗模式并覆盖具体操作，输出新结构和修改记录。

Agent 决定保留哪些组分、修复哪些缺失；工具负责解析、默认相互作用规则、成熟库调用和事实记录。距离窗口不交给 Agent 临时猜。预设可以组合、覆盖，不增加强制预演、人工批准或采样收敛门槛。

不做 MD、对接、配体/金属参数化、pKa 预测或新的 loop 建模算法。清洗成功表示指定操作完成，不表示模型已经适合生产模拟。

## 2. 实现依据与复用

- **Gemmi**：PDB/mmCIF 读写、序列与标识、altloc 和邻居搜索。邻居搜索得到几何接触，不自行证明氢键或配位。[官方文档](https://gemmi.readthedocs.io/en/stable/analysis.html)
- **PDBFixer + OpenMM**：使用 `findMissingAtoms()`、`addMissingAtoms()` 及按需加氢，复用模板和建模能力；缺段由 Gemmi 对声明序列映射并检查定位是否唯一，再转换到 PDBFixer 的 `missingResidues` 插入集合；通过库的缺失集合选择修复对象，不重写模板或补段建模算法。[PDBFixer 手册](https://github.com/openmm/pdbfixer/blob/master/Manual.html)
- **PLIP**：使用其蛋白-配体位点的水桥、金属相互作用候选及几何依据。它不是全结构关键水判定器，其金属距离默认值也不是按元素自适应的配位键长。[功能与规则](https://github.com/pharmai/plip/blob/master/DOCUMENTATION.md)、[默认参数](https://github.com/pharmai/plip/blob/master/plip/basic/config.py)

现有 `format_converter.py` 继续负责格式转换，不隐式清洗。复用 `core/geometry.py` 中适用的纯几何原语；大结构邻居搜索直接用 Gemmi。不得把 `core/irc_path.py` 的共价半径成键判断、RDKit 整分子键感知或反应拓扑变化判据当作水桥/金属配位规则。

两个工具共用解析、选择、探测与规则实现，沿用 registry、schema、路径解析和 `asyncio.to_thread` 调用方式。依赖按可选能力加载；缺库明确报告，不能把未执行的分析返回成“没有发现”。具体版本在真实集成测试后锁定，不在此承诺未验证的兼容范围。

## 3. 结构选择与身份

支持 `.pdb`、`.cif`、`.mmcif` 大分子结构。默认选择第一个模型，输出说明模型总数和所选模型；清洗只输出所选模型。

每个残基返回一个可复制的 `residue_key` 和可读的链名、残基号、插入码、残基名。Key 由工具生成，足以在同一输入中唯一定位；mmCIF author/label 编号转换留在工具内，不要求 Agent 维护两套编号、哈希或映射表。缺段同样用工具生成的 `gap_id` 选择。

探测保留 altloc 及 occupancy，不混合不兼容构象。清洗按残基选择最高占有率构象（按该构象有标签原子的平均 occupancy，排除共有原子，避免较多原子造成偏置），共有原子保留；并列时确定性选择并记录。允许指定 altloc；具体存在性和完整性问题如实报告，不悄悄拼接不同构象。

## 4. `pdb_inspect`

以下为已实现 schema；实际定义见 `Chemtool/pdb_inspect.py` 和 `Chemtool/pdb_clean.py`。

```python
class PDBInspectInput(input_schema):
    input_path: str                      # 必填；绝对路径或工作目录相对路径
    model_index: int = 0                 # 从 0 开始
    chains: list[str] | None = None      # author chain ID；默认全部
    interaction_overrides: dict[str, float] = {}  # 通常省略，规则见下文
```

### 缺失探测

- **已有残基缺原子**：用 PDBFixer 模板列出缺失重原子；蛋白主链 N/CA/C/O、侧链和末端原子（如 OXT）分别返回。未知模板标为 `unsupported`，不能据此宣称完整，也不自动替换修饰残基。
- **内部缺残基**：根据声明序列与坐标映射，返回缺段序列、序列位置、左右已解析残基锚点和证据。使用 PDB 的 SEQRES/缺失注释，或 mmCIF 的 entity sequence、sequence scheme、未观测残基记录；程序将 Gemmi 确定的序列锚点转换为 PDBFixer 所需的插入位置。
- **N/C 端缺段**：分别相对于文件声明的构建体序列判断，不假设它等于天然全长。没有可靠序列时返回 `unknown`；重复序列定位不唯一时保留 `ambiguous`。

编号跳跃或空间断链只报告为提示，不能独立证明缺残基，更不能据此编造序列。每个缺段返回 `gap_id`、`kind`（`internal/n_terminal/c_terminal`）、`residue_names`、序列范围、左右锚点、`evidence` 和 `status`。

### 水、金属及默认规则

默认由工具调用 PLIP 的适用分析，使用其实际版本的距离、角度、原子类型和几何规则。输出规则名称、数值、来源、后端版本及覆盖范围，不把所有接触压成一个通用距离阈值。

- **水**：返回 PLIP 水桥候选、金属相关水，以及补充的极性原子近接候选。附水的 `residue_key`、接触对象、原子名、距离、可用角度、occupancy、B factor、altloc 和候选原因。PLIP 未覆盖的水由 Gemmi 查询蛋白/配体/辅因子的 N/O/S 邻近原子，排除其他水；距离范围复用所用版本的 PLIP 水桥距离规则。这项补充只标为 `polar_contact_candidate`，不声称满足氢键方向或完整供受体条件。
- **金属**：按元素列出金属，包括多原子辅因子内部的金属；返回周围蛋白、水、配体中的候选原子、距离和输入显式连接证据。PLIP 有结果时保留其供体分类及估计几何；另列 Gemmi 找到的 N/O/S 近接候选，采用同版本金属搜索上限，明确标为距离筛选。候选数不等于正式配位数，不据此指定氧化态、键级或力场约束。

PLIP 的 `METAL_DIST_MAX` 是通用候选搜索上限，不能写成各金属的真实配位距离。元素和供体类型必须随候选返回，方便研究判断；若后续采用元素相关规则，应来自明确的成熟工具或规则表并记录出处，不能由 Agent 现场编值。

`interaction_overrides` 仅接受上述分析实际使用的 PLIP 参数名：`WATER_BRIDGE_MINDIST`、`WATER_BRIDGE_MAXDIST`、`WATER_BRIDGE_OMEGA_MIN/MAX`、`WATER_BRIDGE_THETA_MIN`、`METAL_DIST_MAX`（MIN/MAX 表示两个独立键）。值的单位遵循后端：距离 Å，角度度。未提供的值继承后端默认；校验有限值和范围关系，回显生效值。修改规则必须有用户或研究方案依据，常规调用无需填写。

所有水标签均表示几何候选，不是已证实的催化水、稳定结合水或生物功能结论。不依据单一 B factor/occupancy 自动判定重要性。本期只分析文件中所选模型的显式坐标，不扩展晶体对称伙伴；报告这一范围。PLIP 为分析补氢或预处理时仅操作临时副本，记录其影响并把结果映射回原始原子，不将分析副本当作清洗输出。

### 返回

```text
is_success, structure_summary, components,
missing_atoms, internal_gaps, n_terminal_gaps, c_terminal_gaps,
water_candidates, metal_sites, effective_rules,
analysis_status, warnings, message
```

`components` 提供可选择的残基及分类。`analysis_status` 按分析项标明 `completed/unknown/unsupported/unavailable/failed` 和原因；缺库或执行失败时保留已完成结果，但 `is_success=false`。缺序列等科学信息不足用 `unknown` 表达，不伪装成无缺失。输入文件不变，响应不包含整套坐标。

## 5. `pdb_clean`

```python
class PDBCleanInput(input_schema):
    input_path: str                      # 必填
    output_path: str                     # 必填；新 PDB/mmCIF 文件
    purpose: str                         # 必填；研究目的，写入记录
    mode: Literal["preserve", "docking", "md"] = "preserve"
    model_index: int = 0
    chains: list[str] | None = None
    waters: Literal["all", "candidates", "none"] | None = None
    ligands: Literal["all", "none"] | None = None
    metals: Literal["all", "none"] | None = None
    keep_residue_keys: list[str] = []
    remove_residue_keys: list[str] = []
    add_missing_atoms: bool | None = None
    add_missing_residues: Literal["none", "internal", "all"] | None = None
    gap_ids: list[str] | None = None      # 在所选缺段类型中进一步取子集
    replace_nonstandard_residues: bool = False
    add_hydrogens: bool = False
    ph: float = 7.0                      # 仅加氢时使用
    altloc: str = "highest_occupancy"     # 或明确的 altloc ID
    interaction_overrides: dict[str, float] = {}
```

`None` 继承模式默认；显式选项覆盖模式。`purpose` 只记录意图，不让工具再用模型从自由文本猜配置。

| 模式 | 水 | 配体/辅因子 | 金属 | 补已有残基重原子 | 补缺段 |
| --- | --- | --- | --- | --- | --- |
| preserve | 全部 | 全部 | 全部 | 否 | 否 |
| docking | 候选 | 全部 | 全部 | 是 | 否 |
| md | 全部 | 全部 | 全部 | 是 | 否 |

任一模式都能覆盖全部单项，无需再设一个行为相同的 custom 模式。对接要移除哪个共晶配体、MD 要补哪些内部或末端缺段，由 Agent 按任务指定，不由模式一刀切。

选择语义：

- 精确 keep/remove 覆盖组分类别策略，但不恢复被模型/链选择排除的对象；同一对象同时 keep/remove 或选择不存在时明确报错。
- `waters="candidates"` 保留所选构象中报告的水候选，依据删除配体前的环境，方便保留共晶配体附近的水；记录候选来源。分析未完成时不得把未知当作空集合而删光水。
- 水、修饰聚合物、配体/辅因子、单原子金属分别处理，不按 HETATM 一刀切。`metals="none"` 只移除独立金属离子；含金属辅因子整体按配体策略或精确选择处理，不拆其中的金属原子。
- 补缺段必须有可用序列和插入位置。`add_missing_atoms=false` 时，补新残基不能顺便补原有残基；通过库的缺失集合控制，若组合确实不支持则准确报错。

## 6. 执行与输出

执行顺序：解析并合并模式与覆盖项 → 运行所需探测 → 选择模型/链/altloc 与组分 → 按请求替换、补原子/补段、加氢 → 写新结构和修改记录 → 重读核对输出。探测与清洗共享实现，选择器在过滤、建模和写出之间由程序维护映射。

清洗只运行本次操作所需分析：纯选择无需模板分析或 PLIP，补原子/缺段调用 PDBFixer，候选水过滤运行水与金属候选分析；未请求的分析不阻止清洗。补段生成的构象标为 `modeled`；长 loop、末端和金属邻域的不确定性作为说明，不变成一律禁止建模的门槛。加氢不等于全体系 pKa 或金属质子化优化。

```text
is_success, output_path, change_log_path, effective_options,
changes, unresolved, warnings, message
```

修改记录为 `<output_path>.changes.json`，至少包含目的、生效选项/规则、后端版本、输入/输出摘要、删除/替换/新增的残基与原子、构象选择、补段锚点、必要的编号转换和未解决问题。摘要与映射由程序生成，不增加 Agent 入参。

不修改输入，不覆盖已有输出。PDB 表达不了的链名/编号应报明原因并建议 mmCIF，不静默截断。无法保留的实验注释或连接记录在日志说明，不承诺建模后的文件无损往返。

文件、选择器、模板、序列证据或库执行确实有问题时，返回失败阶段、错误原因、已完成与未完成操作；不能跳过请求步骤仍回报成功。可以返回探测信息和诊断产物，但不得把半成品发布为成功结构。

## 7. 调用示例

先探测，所有相互作用规则使用工具默认：

```json
{"input_path":"enzyme.cif"}
```

为含金属活性中心准备 MD 初始结构，保留水、配体和金属，只补内部缺段：

```json
{
  "input_path":"enzyme.cif",
  "output_path":"enzyme_md.cif",
  "purpose":"研究含金属活性中心的底物反应环境",
  "mode":"md",
  "add_missing_residues":"internal"
}
```

对接受体保留候选水和辅因子，明确移除共晶底物：

```json
{
  "input_path":"complex.pdb",
  "output_path":"receptor.cif",
  "purpose":"受体对接准备，移除共晶底物并保留候选水和金属",
  "mode":"docking",
  "remove_residue_keys":["<从探测结果复制的底物 residue_key>"]
}
```

## 8. 开发落点与验收

新增 `Chemtool/pdb_inspect.py`、`Chemtool/pdb_clean.py` 两个薄封装；共同解析、探测与修复放在 `core` 中，不复制规则。登记 registry、可选依赖及相关测试，保留现有工具 schema 和异步执行约定。

验收以本地真实 PDB/mmCIF fixture 和真实后端调用为准：

1. 区分主链、侧链、OXT 缺原子及三类缺段；未知模板不报完整，无序列时末端为 unknown，编号跳跃不冒充缺段。
2. 等价 PDB/mmCIF 得到相同语义；插入码、author/label 差异、多模型、altloc 选择均可正确定位和回溯。
3. 水桥、金属相关水、普通近接水分别返回规则与依据；无配体时不伪造 PLIP 水桥；距离候选不冒充确定氢键或配位。
4. Agent 不填距离即可运行；后端默认和显式覆盖均可追溯。蛋白、水、配体供体和含金属辅因子均覆盖，兼容构象不混用。
5. 预设与覆盖、精确保留/删除、只补内部或指定缺段、只补新残基不补旧残基均按请求执行。真实不支持的组合明确失败。
6. 原件字节不变，输出可重读，原子/残基变更与日志对应；失败不返回假成功，未完成的候选分析不造成误删。
7. registry/schema 可发现且不强制导入重依赖，调用不阻塞事件循环。缺少可选库的集成测试明确 skip，不用 mock 声称集成通过。

本地只运行相关模块检查和测试。提交、推送、创建 PR 和合并遵循用户当次授权，推送或创建 PR 不代表允许合并。


## 9. 本地实现说明

- `residue_key` 直接采用 Gemmi 的原生残基地址文本，例如 `A/ALA 12A`。仅在同一所选输入确实有重复地址时加链/残基索引后缀。工具精确查表，不要求 Agent 理解或组装地址、维护 author/label 映射、版本或哈希。
- 两工具共用 `core/pdb_structure.py`（解析和选择）、`core/pdb_workflow.py`（执行与新文件发布）、`core/pdb_repair.py`（Gemmi 序列证据和 PDBFixer 修复）、`core/pdb_interactions.py`（实际 PLIP 规则和 Gemmi 邻居查询）。`format_converter` 不变。
- 可选依赖集为 `cloudra[pdb]`，本地实际验证并锁定 Gemmi 0.7.5、PDBFixer 1.12.0、OpenMM 8.6.1、PLIP 3.0.1、OpenBabel 3.2.1。不导入这些库也可发现工具及 schema。纯模型/链/组分选择只需要 Gemmi。
- 缺段依据为文件声明的构建体完整序列及保留的 label 序列锚点。单有 REMARK465 或未观测残基表、但没有完整声明序列时仍报告 unknown，不猜测末端全长或修复序列。编号跳跃不会生成缺段。
- 保留多个 altloc 的探测会逐构象检查缺原子，Gemmi 几何候选只连接兼容 altloc。PLIP 对共有原子与每个单独 altloc 分别运行临时副本，再映射回原始对象并去重，不把互斥构象放在同一次分析中。清洗保留选中构象的原始标签，候选水筛选仍检查原始构象兼容性。
- PLIP 的分析副本使用临时 PDB，因此分析坐标精度为 0.001 Å；原始 atom/residue 身份通过程序映射，原输入不变。超出该临时表示能力时如实报告，不截断原始输出标识。
- 新文件在临时路径写出并重读核对后，以排他方式发布结构和修改日志。日志记录失效连接删除和实验注释写出前后清单；不承诺实验注释无损往返。

本地集成还覆盖 PLIP/OpenBabel 与项目已有可选 RDKit 的原生库加载顺序：真正运行 PLIP 时先初始化环境中已安装的 RDKit，再加载 OpenBabel，避免已复现的反向加载崩溃；未安装 RDKit 不新增该依赖，schema 发现仍不加载原生库。
