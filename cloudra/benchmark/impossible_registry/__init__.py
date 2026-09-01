"""impossible 档任务登记表（按族组分文件，避免并行登记冲突）。

每个子模块导出 `TASKS: dict[str, dict]`，键为池内 id（如 "A1"），值为
impossible 正选题与其兄弟题（sibling 对照题）的全部机器契约：

- `name_zh`: 池内 md 条目标题（生成器与 impossible.md 头行做全等校验，
  防登记与题源漂移；标题取去掉尾部【…】标记与最后一个（英文）括注后）。
- `name_en`: 题名英译。
- `kind`: "reaction"（反应/机理题，走机理图协议）或 "property"（物种/态
  能量题，走过程图协议——节点为物种或电子态、边为态变化）。
- `question_en`: 题面英文（问什么；不泄漏"本题多参考"的答案）。
- `deliverable_en`: 最终摘要必须报告的量（含单位与参考态；后接统一的话
  语允许在方法不可信时明确拒答——impossible 与 sibling 同款措辞，不泄题）。
- `conditions_en` / `charge` / `multiplicity` / `closed_shell`: 系统规格。
- `reactants` / `products`: 无映射 canonical SMILES 列表（节点身份；property
  单节点题 products == reactants）。
- `mapped_reactants`: query 展示的原子映射反应物 SMILES（有键变化推导的
  步骤才需要；参与键变化的 H 以显式 [H:n] 给出）。
- `reactant_accessible`: 反应物节点是否在允许方法下可达（缺省 True）。
- `steps`: 过程步列表，每步 {"out": <映射 SMILES>, "type": <step_type
  英译>}；可选键：
    - "with_ts": bool（缺省 False；True 时边带 TS 节点，False 时 via=None，
      适用于态变化/解离极限这类无一阶鞍点的过程）；
    - "ts_accessible" / "node_accessible": 该步 TS 节点/输出节点的可达性
      （缺省 True；False = 该节点对应的请求量在单参考/白名单方法下不可信，
      进入 gold_inaccessible_nodes）；
    - "conformational": True（无键级变化的态变化，bond_changes 双空）；
    - "no_mapping": True（笼状价异构等键重组无法从 SMILES 级映射差集推导
      键变化——显式声明，bond_changes 留双空，不冒充构象步）。
  末步 out 去映射后必须等于 products。
- `wrongly_solve_penalty`: "high"（铁板 MR 题）/ "medium"（灰色地带题）。
- `evidence_strength`: "ironclad" / "gray_zone"（定稿风险登记：灰色题的
  多参考论断为机理外推，judge 评估必须连同证据强度一并给出）。
- `sibling`: 兄弟题登记（同构，去掉 sibling/wrongly_solve_penalty/
  evidence_strength 三键；全部节点必须 accessible=True——校验强制）。

粒度规则：gold 边 = 一个造成重原子骨架键变化的事件或一次被考察的态变化；
bond_changes 由生成器从相邻步映射 SMILES 差集自动推导，禁止手填（唯一
例外是显式 no_mapping 声明的键重组步）。
"""

from cloudra.benchmark.impossible_registry import abc, defg, hij

REGISTRY: dict[str, dict] = {}
for module in (abc, defg, hij):
    overlap = set(REGISTRY) & set(module.TASKS)
    if overlap:
        raise SystemExit(f"impossible_registry 登记重复: {overlap}")
    REGISTRY.update(module.TASKS)
