# PDB 清洗后的 MD 支持计划

状态：规划草案，未实现。代码盘点基于 `master@317d90f0993df0123e37d8e59c75cc3da9ada77a`（2026-11-08，PDB 工具已合并）。本文只规划经典 MD；具体体系、力场与模拟协议需在实施前确认，不把建议写成已批准的科学选择。

## 1. 目标与边界

打通一条可复现的实际流程：

`pdb_inspect → pdb_clean → 化学状态与参数准备 → 建系/溶剂化 → 最小化/平衡/生产 → 轨迹分析`

近期交付目标是从清洗后的结构得到可运行体系、真实轨迹及可检查的分析结果。先完成一个标准可溶蛋白的闭环，再扩到蛋白–配体；金属、共价配体、膜、增强采样、自由能和 QM/MM 分别按真实需求推进。经典固定拓扑 MD 不承担化学反应断键成键，也不替代已有 QM/TS 科学验收。

不增加第二套任务账本、调度器、状态机或通用多引擎插件层。成熟 MD 库负责算法；Cloudra 负责结构语义衔接、输入产物、已有作业系统接入和结果解释。

## 2. 已有能力与真实缺口

| 环节 | 当前代码已具备 | 尚缺什么 |
| --- | --- | --- |
| 结构探测与清洗 | PDB/mmCIF 读写；模型/链/altloc/组分选择；缺原子与缺段探测；按请求补重原子、补段、加氢；水/金属候选；新结构及修改日志 | 确定本次模拟的生物学组装、末端/断链处理、质子化微态及特殊连接。清洗不承担力场参数化 |
| 输入表示 | 清洗保留大分子结构语义；已有格式转换、小分子结构构建和构象搜索 | 把清洗结构中的残基、配体身份与 MD topology 的原子顺序连起来；保留配体键级/形式电荷及原始结合姿态 |
| 建系 | `cloudra[pdb]` 已包含 OpenMM，供 PDBFixer 修复使用 | 力场模板匹配、配体参数、拓扑/Hamiltonian、周期盒、溶剂和离子；可重载的完整 MD 输入产物 |
| 运行 | `submit_compute_job(job_type="shell")` 已接入本地、SSH、Slurm；有 CPU/内存资源声明、日志、查询、取消和终态通知 | MD 阶段脚本、原生 checkpoint 续跑及阶段产物。GPU 资源尚无完整声明/调度契约 |
| 结果 | 现有文件产物和通用作业查询可复用 | 温度/能量/密度等实际数值，PBC 处理、对齐、RMSD/RMSF、指定接触及抽帧；区分执行完成和科学上足够的采样 |
| 方法指导 | 已有 `molecular-dynamics-simulation` skill | 修正与当前代码不一致的执行说明及过于绝对的科学规则；让示例与实际阶段和工具一致 |

### 两个不能误接的边界

1. **`pdb_clean(mode="md")` 不是 MD 建系。** 当前默认保留全部水/配体/金属并补重原子；默认不补缺段、不加氢。成功仅表示请求的清洗操作完成，输出是结构和 `.changes.json`，没有力场、电荷参数、拓扑或溶剂盒。即使显式加氢，也只是 PDBFixer/OpenMM 的规则，不是完整 pKa/金属质子化求解。
2. **`conformer_search` 不能直接接整个清洗后的蛋白 PDB。** 当前结构入口是 SMILES、XYZ、SDF/MOL，后端是 RDKit/CREST，输出 `confs.sdf` / `confs.xyz` 和构象能量表。它可在确有需求时处理独立小分子配体，但不负责蛋白拓扑、周期体系或时间轨迹。对共晶配体，参数化默认保留原有重原子结合姿态，不先做构象重生成。

现有构象文件、格式转换和 MD topology 不能互相替代。尤其不能先把整蛋白转成 XYZ，再让小分子成键推断替代残基模板与已知连接。

## 3. 先复用已有运行入口

以下是当前真实支持的最小提交方式，`run_md.sh` 需先由准备流程产生；该示例不表示 MD 准备器已经存在：

```json
{
  "input_file": "md/run_md.sh",
  "job_type": "shell",
  "is_async": true
}
```

CPU/内存使用现有 `cpus`、`memory_mb`；远端使用已有 `node_id`，本地/Slurm 使用 `execution_backend`，不再包装一套 MD 提交工具。脚本负责环境与 MD 命令，`shell` 作业成功依据退出码，不能据此宣称体系已平衡或采样已收敛。

当前执行器实际分支（`cloudra/calculator.sh`）：

```bash
    shell)
        exec bash -- "$INPUT_FILE"
        ;;
```

当前 MD skill 仍写着 `submit_compute_job` 不能调度任意 MD 脚本，与该入口不符，应在接入时同步修正。依赖包含 OpenMM 也不等于已提供生产 MD 工作流。

## 4. 分阶段实现

### 阶段一：标准蛋白的最小闭环

**建议先使用 OpenMM**：当前可选依赖已具备它，与 PDBFixer 衔接直接，适合先以真实 CPU 小体系验证。GROMACS 是后续需要时的另一执行路线，本期不同时抽象两套引擎。

1. 选一个有明确来源、规模小、无特殊残基和金属参数需求的真实 PDB/mmCIF fixture。确定模拟的是哪一组装/链，清洗后检查补建区域与端点；不自动把单链或晶胞当成完整生物学体系。
2. 在选定力场下确定质子化、组氨酸变体、末端和二硫键。已有加氢结果按本次模板核对，不仅依据 `ph` 推断所有微态；不重复造一套清洗器。
3. 通过 OpenMM 成熟 API 建拓扑与 System、加溶剂和离子。确认每个保留组分有参数，记录总电荷、原子数、盒向量、模板来源与实际配置。水和离子参数必须与所选体系/力场相容。
4. 生成独立目录内的结构/拓扑、序列化 System、科学配置和 `run_md.sh`/运行脚本。所有依赖文件同行；不要只存一个无法单独恢复运行的 PDB 或 checkpoint。
5. 明确实现最小化、热化/平衡和生产各阶段的时长、系综、约束/约束释放、积分器及输出。从已确认方案生成脚本，不用固定“多少 ps 必然平衡”的规则冒充科学判断。
6. 通过现有 `shell` 提交短轨迹，写出日志、最终结构、轨迹、checkpoint、进度和结果摘要。续跑从引擎真实状态恢复时间/步数，避免重复最小化或重新随机化速度。

产物至少包含：可重载的拓扑与坐标、参数化 System、运行配置/脚本、轨迹、checkpoint、阶段数值日志。OpenMM 二进制 checkpoint 的引擎/平台兼容性如实说明，另保留可移植的结构/System/状态；不承诺跨平台逐位一致。

**验收**：真实后端完成一个短体系的建系、最小化、平衡、生产和一次续跑；重新加载产物时原子/残基对应正确，能量与坐标有限，步数/物理时间/轨迹帧数一致。短 smoke test 只证明链路能跑，不能证明生产采样充分。

### 阶段二：让结果能回答问题

复用 MDAnalysis 或相应引擎分析工具，按需要实现：

- 先按拓扑/盒处理跨周期边界，再按明确的原子选择对齐；对齐选择与测量选择分别记录。
- 输出能量、温度、体积/密度时间序列，以及 RMSD、RMSF、用户指定接触/距离和代表帧。
- 明确分析时间区间、参考结构、单位和选择。平衡段如何排除、是否采用分块或独立重复，由研究方案与实际数据决定，不硬删前 20%，不把帧数当独立样本数。
- 轨迹按帧读取，完整数组/图表落盘，工具只返回简短摘要与文件路径。

**验收**：已知刚体平移/旋转和跨盒轨迹的结果正确；帧索引、时间与抽帧结构对应；能区分计算失败、部分完成和分析完成。暂不实现自由能排名或自动“已收敛”结论。

### 阶段三：蛋白–配体及实际运行规模

1. 将配体结构与 PDB 残基明确对应。SDF/化学模板承担键级、电荷、立体信息，PDB/mmCIF 承担结合姿态；原子映射由程序生成和验证，不交给 Agent 手填编号表。
2. 经用户确认后只选一条小分子参数化路线（如 OpenFF 或 GAFF2/AmberTools），验证与蛋白/水/离子参数兼容。处理明确的质子化/互变异构体和净电荷；保留方法、版本及参数产物。
3. 共价配体、辅因子和金属位点单独处理。PLIP 接触不能自动变成配位键、氧化态、电荷或约束参数；无适用模型时指出具体缺项，不删除组分或套 UFF 掩盖问题。
4. 再验证实际目标节点。现有提交 schema 没有 GPU 请求，Slurm 渲染器也没有 `--gpus`/`--gres`；共享 GPU/HPC 运行前，在现有资源声明、节点容量和 Slurm 生成处补最小 GPU 契约，不能只在 Python 中选择 CUDA 就宣称完成调度适配。
5. 远端目前会回传全部作业产物。先用短轨迹验证 staging/续跑；生产轨迹规模确有需要时，再在现有传输路径增加明确的产物选择或按需取回，不新建文件平台。

**验收**：一个真实非共价蛋白–配体体系跑通，配体键级/净电荷、原子对应和起始姿态正确；CPU/目标 GPU 的实际使用与申请一致；中断续跑与远端产物可读。金属和共价体系另建适用 fixture，不能用普通配体验收代替。

## 5. 工具接口保持小

先写一条可测试、可重复运行的准备/运行/分析实现，再接现有 registry。建议最终最多增加两个入口，以下为**拟议语义，不是已实现 schema**：

| 入口 | Agent 必要输入 | 返回 |
| --- | --- | --- |
| `md_prepare` | 清洗结构路径、输出目录、明确的建系和模拟方案；配体阶段再增加配体结构/参数 | 完整准备目录、可提交的 shell 脚本路径、体系摘要、实际缺项 |
| `md_analyze` | 拓扑/轨迹路径、参考结构、分析选择和时间区间、输出目录 | 数值摘要、分析文件/图表、抽帧结构路径 |

建系和模拟方案只包含必要科学参数：力场及模板、微态/特殊连接选择、溶剂盒和盐条件、阶段/时长/温压、积分器/时间步/约束、输出频率。实施时用明确类型表达；不要将它变成任意后端参数大字典，也不要为了缩短表面接口把同一堆配置藏进不透明的 `config_path`。

力场选择和科学阈值不在本文擅定。哈希、版本采集、原子映射、作业 ID 关联由程序生成。随机种子是可记录/可设置的模拟参数，不与内部并发字段混为一谈。

运行、查询、取消和通知复用已有计算工具；checkpoint 在原生运行脚本中消费。先不加 `md_validate`、`md_resume`、多模式路由器、额外审批/锁/租约协议。错误直接指出不匹配模板、缺失参数或不可用依赖，保留原始错误信息；必要的物理约束与产物一致性检查属于科学正确性，不堆叠防御性状态分支。

## 6. 落点与测试

- 新的 MD 准备/分析薄工具放 `cloudra/tools/Chemtool/`，共享科学处理放 `cloudra/tools/core/`。第一版仅承接一个真实后端，不改写 PDB 清洗、格式转换或构象搜索职责。
- 工具注册沿用 `cloudra/tools/registry.py`，路径沿用 `resolve_tool_path`，耗时库操作离开事件循环，长模拟走现有 job system。
- 更新 `cloudra/skills/molecular-dynamics-simulation/SKILL.md`：更正 shell 路线；核对“严格要求某水模型”等绝对断言；让示例真正包含所宣称的升温、约束释放和 NPT 平衡阶段；自由能估计保留适用条件与不确定性。
- 新依赖仅按实际选择加入可选依赖。OpenMM 已存在；不先同时装齐 GROMACS、AmberTools、OpenFF、MDAnalysis 等所有路线。
- 单测覆盖身份/单位/参数传递和脚本阶段；真实小体系覆盖建系、运行、续跑和分析；目标远端使用同一行为用例。缺可选依赖应明确 skip，不用 mock 声称 MD 集成通过。
- 本地只跑新增/受影响模块检查和测试，保留现有 PDB/提交作业相关回归，遵守仓库不跑本地全套测试的约定。

## 7. 开工前需要确定的科学范围

集中确认一个真实目标体系及其研究问题、首条参数化路线、力场/水/离子组合和模拟条件。若先做标准蛋白 CPU 闭环，可暂不决策配体和金属路线，也不阻塞基础实现。任何具体数值都以该方案或所选后端的明确适用默认为依据，不由 Agent 临时编定。

优先顺序：**先补“清洗结构 → 参数化体系”的断点，再完成短 MD 与分析，最后扩大体系和算力范围。**

## 8. 代码证据

以下链接固定到盘点版本，避免后续代码变化使“当前已有”失去依据：

- [PDB 清洗接口与默认行为](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/tools/Chemtool/pdb_clean.py)，[清洗流程与产物](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/tools/core/pdb_workflow.py)，[修复与加氢](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/tools/core/pdb_repair.py)。
- [构象搜索输入/后端/输出](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/tools/Chemtool/conformer_search.py)，[格式转换边界](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/tools/Chemtool/format_converter.py)。
- [提交作业 schema](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/tools/Chemtool/submit_compute_job.py)，[shell 实际执行](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/calculator.sh)，[SSH 传输与完成判定](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/runtime/remote_compute.py)。
- [节点调度字段](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/services/nodes.py)，[Slurm 脚本生成](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/infra/slurm.py)。
- [MD skill](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/cloudra/skills/molecular-dynamics-simulation/SKILL.md)，[当前可选依赖](https://github.com/yyywaa/Cloudra-mechanism-agent/blob/317d90f0993df0123e37d8e59c75cc3da9ada77a/pyproject.toml)。
