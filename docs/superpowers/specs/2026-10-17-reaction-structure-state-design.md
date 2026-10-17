# 反应结构与原子映射统一：减法改造方案

日期：2026-10-17。状态：方案已获批准并完成实施；下文保留原设计说明，当前定义以源码为准。

## 目标与范围

同一条反应中，程序保存并维护一份当前结构与全原子对应；工具引用这份状态，Agent 不再复制映射、结构摘要、坐标文件和编号换算结果。

第一落点是已有 TS run，覆盖结构导入、构象处理、反应映射、路径/插值初猜、QM 输入生成、计算结果接收和科学验证。沿用现有 run_id、数据库、Molecule、作业账本和阶段依赖，不建立全局结构注册中心、隐式 active run、通用 manager 或第二套计算队列。

普通单分子计算、未知产物的探索扫描、一次性文件分析继续可独立使用。它们在导入边界构造相同的内部结构值，不为此创建或启动 TS 管线。

科学方法、候选选择、反应坐标、扫描范围和预算仍是研究输入；版本、哈希、原子换序及证据归属由程序维护。科学验收规则和阈值不在本次改造中调整。

## 当前实际问题

`TsProcessRecord` 同时保存 input、input_binding、structures、seed_molecules、current_seed_* 和 product_seed_*。映射在 input.reaction.atom_map 中，验证后又被复制到 input_binding；原子表既是模型视图又被阶段函数读取。独立 ts_guess 再从文件建立结构，映射处理与 TS 管线各有实现。

已有 Molecule 可持久保存完整图、原子属性和坐标，CandidateRecord 也已把原子/组分身份放到 Mol 属性中，因此应延续该基础，不再造元素、坐标、键或全局结构 ID 的并行载体。

## 一份当前状态

将现有 record.structures 从可写的展示字典改为内部类型。以下为拟议定义，非当前代码：

```python
from pydantic import BaseModel, ConfigDict, StrictInt

from cloudra.tools.core.molecule import Molecule


class ReactionStructures(BaseModel):
    model_config = ConfigDict(extra="forbid")

    # 允许建模尚未完成；完整分子包含图、原子身份和坐标。
    reactant: Molecule | None = None
    product: Molecule | None = None

    # 只保存一份已确认的完整对应：产物行号 -> 反应物行号，内部统一 0-based。
    # None 表示尚未确认，不能默认为恒等映射。
    product_to_reactant: tuple[StrictInt, ...] | None = None

    # 当前选定的 TS 初猜也使用同一分子载体，不再靠目录里“最后一个文件”决定。
    candidate: Molecule | None = None
```

这份对象随现有运行记录持久化，不是新数据库实体。当前声明版本、运行版本继续由程序管理。

映射属于两份具体结构的对应关系，不写成单个 Mol 的永久跨反应属性。构建原子身份沿用现有 AtomIdentity / Mol 原子属性；首次图到具体坐标的绑定只在导入或结构改变时处理。只有现有完整身份与映射校验通过，才写入 product_to_reactant。图未知、身份不符或对应有歧义时，沿用现有 blocked 与诊断，不能把装进 Mol 当作科学确认。

源文件、读入字节、导入排列和哈希保存在现有声明/导入快照与证据中；它们解释来源，不再作为随时回读的当前几何。正式优化、频率和 IRC 结果仍属于对应作业及其不可变证据；接收新帧时继承可证明的原子身份，继续独立执行现有收敛、图身份和方向验证，不把 TS/IRC 帧强行认成某个端点最低点。

## 具体删减

| 当前内容 | 处理 |
| --- | --- |
| seed_molecules | 并入唯一的 record.structures，删除平行存储 |
| 持久化 input_binding | 删除缓存；校验通过的对应只写一次，失败写现有 blocked，历史证明保留在证据中 |
| structures 中 atoms、atom_count、components、重复 binding_status 等 | 改为从分子与当前绑定临时生成的只读视图 |
| current_seed_xyz_path/current_seed_mol_path/product_seed_xyz_path/product_seed_mol_path | 删除当前结构指针；需要文件时从当前 Mol 导出到 run 内 |
| current_reactant_prepared_path | 删除当前数据入口用途；构建身份导入 Mol，原构建文件作为来源产物保留 |
| current_ts_guess_path 与目录扫描猜测当前候选 | 当前候选改由 candidate 持有；选定帧及来源保留在现有产物/证据记录 |
| effective_reaction_center | 按已有研究声明和 guidance 规则派生，不再另存一份可写值 |
| 当前声明中的 reaction.atom_map、重复 heavy_atom_binding 数组 | 完整具体映射候选机制接通后删除模型搬运入口；历史声明原样保留 |
| normalization.pending/applied、源文件覆盖意图、字节回滚、恢复分支 | 停止覆盖用户源文件后删除 |
| TS 与独立插值/路径工具中重复的端点检查和重排实现 | 收成同一组内部函数，由调用方传入 ReactionStructures |

保留：研究声明、原始来源快照、实际作业输入路径、job ID、实际计算配置、声明版本、attempt_history、日志及冻结 atom_binding。它们记录不同历史事实，不能当成重复状态删掉。

## 函数怎样取数据

在一个小的 core 模块中定义 ReactionStructures 和必要的结构操作；复用 molecule.py 的 copy_conformer、with_positions、renumber_atoms、to_xyz。阶段函数仍负责调度和落盘；化学变换函数只读取结构值并返回新值，不查询会话、数据库或任意工作区文件。

拟议的路径端点视图如下，内部 API，尚未实现：

```python
from cloudra.tools.core.molecule import copy_conformer, renumber_atoms


def path_endpoints(state: ReactionStructures) -> tuple[Molecule, Molecule]:
    # 未确认两端和对应关系时，由现有流程返回缺失/歧义诊断。
    if state.reactant is None or state.product is None or state.product_to_reactant is None:
        raise ValueError("两端结构及其全原子对应尚未确认")

    # 映射在写入状态时已验证完整、元素吻合；这里仅求逆排列，不重复做化学决策。
    order = [state.product_to_reactant.index(i) for i in range(state.reactant.GetNumAtoms())]

    # 返回副本；路径算法拿到同序端点，不修改权威状态，也不再要求 Agent 换序。
    return copy_conformer(state.reactant), renumber_atoms(state.product, order)
```

插值和 xTB 路径都使用这一视图；缺少 xTB 后转插值也使用已取得的视图，不再套用第二次映射。QM renderer 直接读取相应 Mol；只有引擎文件/执行边界导出 XYZ、MOL 或原生输入。ORCA/Gaussian/xTB 的编号转换只在统一边界处理，内部关系均为 0-based。

对外原子表从相同对象生成，仍提供人类可读的 1-based 编号、真实结构身份和来源。模型看见的表不再反过来充当执行输入。

## 工具与 Agent 的变化

已有运行上的反应工具以 run_id 取状态，删除该调用形式中的两端 path/text、atom_map、重复电荷/自旋等参数。研究选项保留。例如拟议调用：

```json
{"run_id": "ts_0007", "mode": "xtb_path"}
```

```json
{"run_id": "ts_0007", "selected_candidate": 2}
```

分别对应 ts_guess 的路径研究和 reaction_mapping 的歧义选择；为拟议合同，不是当前可用调用。需要操作新文件的一次性分析保留独立来源形式，采用与 run 引用互斥的输入 schema；不能同时提交 run_id 又覆盖这份 run 的两端文件/映射。入口只负责导入，内部进入相同结构/映射函数，不另保留旧的文件算法。普通 QM 不需要 run_id。

已有 run 的写操作统一经过现有修订事务和推进驱动：路径研究先更新 guess 意图，再由已有队列提交；候选选择作为结构绑定修订处理，相应证据按既有依赖失效。工具不能另开直接写状态的路径，也不能绕开运行中作业的既有保护直接执行 runner。

ts_prepare/ts_resume 在内部自动尝试现有映射算法：唯一且完整验证通过时直接保存，不再要求 Agent 额外调用工具并复制结果。真实歧义时，候选必须描述“当前两端具体分子的完整对应”，包含具体图到坐标的绑定及全原子对应；不能只给 SMILES 重原子候选，却让 Agent 另填 heavy_atom_binding。复用 selected_candidate 的研究选择语义，省略时不暗选第 0 项。Agent 不填写候选版本或哈希。

reaction_mapping 统一按 WRITE 工具登记，沿用现有 run 归属与提交检查，撤销 Supervisor 的 evidence_read 入口；Supervisor 查看当前结构和候选走 ts_inspect。独立分析形式仍不写持久状态，但不为这一分支新建动态权限机制，也不增加 write/commit 开关。

来源设置采用局部补丁：省略保留、null 清除。FileConformer 不再作为必须整块重填的修改单位；来源补丁按当前 kind 合并，再用完整源定义校验。取消已有预优化应能直接提交：

```json
{
  "run_id": "ts_0013",
  "changes": {"conformers": {"product": {"optimization": null}}},
  "reason": "使用已导入的端点结构，取消额外预优化"
}
```

这是拟议行为，不能仅删除 _ATOMIC 中的一行就宣称实现；需同时处理当前来源种类的补丁解析。原有 MOL、来源和已确认绑定由程序保留或按实际变化失效。

## 更新规则与历史

| 变化 | 当前结构与映射 | 证据处理 |
| --- | --- | --- |
| 仅修改计算设置或取消预优化 | 不重新导入结构，不要求重填对应关系 | 按现有计算依赖失效 |
| 新坐标，完整原子身份已证明不变 | 返回更新坐标的新 Mol，保留对应 | 旧坐标产生的受影响计算按既有依赖失效；旧原始结果保留 |
| 文件仅换序且对应可证明 | 在内部一次重排到既有原子身份；本次显式坐标编号只转换一次 | 不因编号可证明就宣称旧计算可复用；本轮沿用现有阶段依赖规则 |
| 改变物种、图、电荷、自旋或无法证明原子身份 | 重新执行现有身份/映射检查，不继承未经证明的旧绑定 | 保留旧尝试及其结构/映射快照，不能用当前映射解释旧日志 |

源文件修改不会偷偷改变已导入状态；用户明确在修订中提交该来源时才读新字节，即使路径字符串未变也识别为一次导入操作。仅改其他字段不重读原来源。

一次导入产生归一后的分子、来源快照和修订结果；现有事务核对程序持有的 revision 与作业状态后接受。停止覆盖调用方文件后，移除反复投影和字节回滚流程；保留必要的并发检查。沿用现有 _DEPENDENTS，不新增通用依赖/失效框架。

计算提交时由当前状态生成一次不可变结构/映射绑定，原生日志继续绑定对应声明版本。DAG 从这些证据独立验收，不因共享了结构对象就自动通过。

## 实施顺序

1. 在核心结构模块建立唯一内部状态与复制/导出视图，先用持久化、同序端点及不修改输入的测试固定语义。
2. 切换 TS build/map/guess 和输入生成到该对象，解析作业输出时保留真实来源；同批删除旧字典、指针和重复重排，不长期保留双写。
3. 把映射生成与具体绑定收成共同内核，接通具体候选选择，调整工具的 run 引用合同和局部来源补丁；同步更新角色权限、schema、SOP及失败恢复提示。
4. 停止覆盖用户源文件，删除重写恢复协议、重复投影和依赖展示表执行的代码；保留现有作业提交与阶段依赖。
5. 验证历史证据与 DAG 桥接，完成聚焦测试及代码审查。

涉及的主要源码：core/molecule.py、core/reaction_state.py（拟新增的小模块）、core/ts_inputs.py、core/ts_process.py、core/ts_revision.py、core/ts_pipeline_driver.py、services/ts_pipeline_store.py、Chemtool/ts_search_process.py、Chemtool/ts_guess.py、Chemtool/reaction_mapping.py，以及相关输入 renderer、工具注册/说明和聚焦测试。

## 验收与交付边界

- 同一 run 中映射/插值/xTB/QM 输入读取同一结构；后续调用不出现 Agent 复制 atom_map 或重填旧来源的步骤。
- 有原子换序的端点，xTB 与插值获得相同的正确顺序；xTB 缺失回退时不会二次映射。
- 真实映射歧义仍需选择，具体文件绑定歧义不能被 SMILES 候选索引掩盖。
- 换坐标、换序、换物种分别按上述规则处理；源文件与历史输入/日志字节不被覆盖。
- Mol 持久化保留图、同位素、原子属性和精确坐标；修改返回副本，不污染当前或历史状态。
- 失败、停止、等待、候选与科学 verified 的区别不变；普通单分子计算和独立探索无需创建 TS run。
- 补充零 API-key 场景，验证整条自动续接与一次歧义选择；不以模型自然语言措辞作为断言。
- 本地只做 compileall、Ruff 和相关模块测试，不运行全套。

这是内部持久格式变化。实施时安排一次性、可核对的 checkpoint 转换，只有能够证明结构/映射关系的数据才转换；不可确证的历史保留原始证据只读，不保留两套推进逻辑或兼容开关。本方案阶段不迁移实际数据、不重启服务、不触碰正在运行的计算。


## 实施验收记录

已切换到 format 7 的唯一 ReactionStructures，删除旧缓存、当前文件指针、公开映射搬运字段以及源文件覆盖/恢复协议。完整具体候选覆盖氢迁移与同位素；候选重选不会被上次派生绑定缩窄。源文件不覆盖，当前原子表临时派生，作业结构/映射在提交时冻结，频率完成时仅补日志摘要。

独立审查发现的生成物种未重建、旋转分支身份检查及频率/IRC日志绑定问题均已补回归修复。相关模块合跑 1050 passed、4 skipped；compileall、Ruff、git diff --check 通过。

新增 scripts/migrate_ts_structure_state.py 仅支持显式离线 JSON 检查点转换，拒绝无法证明的旧状态，并保留原文件；本次未迁移实际数据或重启服务。
