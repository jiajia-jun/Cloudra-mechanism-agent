# 有机机理 / 副反应知识库 Schema（v2 — 含 tags 分类体系）

目标：扩展现有 chem-kb，让 agent 能回答「这个反应常见机理是什么？可能有哪些副反应路径？什么条件下抑制/促进？这个反应和计算化学怎么衔接？」。

与计算化学知识库共用同一张 `kg_entities` / `kg_relations` 表与同一份 `cards.jsonl` 向量索引。有机知识以 `org:` 前缀与既有 `kb:` / 计算化学实体隔离，后续统一检索。

## 实体类型

| type | 说明 | id 约定 | 必填 |
|---|---|---|---|
| `reaction` | 命名反应或通用转化 | `reaction:<标准英文名>` | label, props |
| `molecule` | 反应物/产物/副产物/中间体/试剂/催化剂 | `molecule:<标准名>` | label, smiles?, props |
| `mechanism_step` | 基元步骤 | `mechanism_step:<反应英文名>#<序号>_<步骤名>` | label, props |
| `side_pathway` | 竞争通道 | `side_pathway:<反应英文名>#<副路径名>` | label, props |
| `condition` | 温度/溶剂/碱/气氛/配体/光照等 | `condition:<描述>` | label, props |
| `functional_group` | 选择性锚点官能团 | `functional_group:<名称>` | label, smiles?, props |
| `total_synthesis_case` | 经典全合成案例 | `total_synthesis_case:<目标分子>` | label, props |

## 关系类型

| rel_type | 含义 | src → dst |
|---|---|---|
| `produces` | 生成主产物或副产物 | reaction → molecule |
| `proceeds_via` | 经由机理步骤 | reaction → mechanism_step |
| `step_next` | 步骤顺序 | mechanism_step → mechanism_step |
| `involves` | 步骤涉及物种 | mechanism_step → molecule |
| `competes_with` | 副路径与主反应竞争 | side_pathway → reaction |
| `common_side_of` | 副产物归属于 | molecule → reaction |
| `favored_by` | 条件促进 | side_pathway/reaction → condition |
| `suppressed_by` | 条件抑制 | side_pathway → condition |
| `requires` | 必要条件 | reaction → condition |
| `applies_to` | 机理/反应适用官能团 | reaction/mechanism_step → functional_group |
| `alternative_to` | 可选替代 | reaction → reaction |
| `uses_catalyst` | 使用催化剂 | reaction → molecule |
| `illustrates` | 全合成案例展示该反应 | total_synthesis_case → reaction |
| `targets` | 全合成目标分子 | total_synthesis_case → molecule |
| `relevant_to_compchem` | 与计算化学方法的衔接点 | reaction/side_pathway → concept/method（复用计算化学实体 id） |

`evidence_level`：L0=文献/教材常识，L1=计算验证，L2=模型假设。默认 L0。

## props 字段约定（JSON）

**所有实体的 props 都必须含 `tags` 数组**（controlled vocabulary，见下节）与 `label_en`。

reaction:
```json
{
  "label_en": "Heck reaction",
  "class": "cross-coupling",
  "tags": ["class:cross-coupling", "mechanism:organometallic", "metal:Pd", "bond_formed:C-C", "reactant_type:aryl_halide", "reactant_type:alkene"],
  "summary": "Pd催化芳基/乙烯基卤与烯烃的偶联，经氧化加成/迁移插入/β-H消除循环",
  "typical_yield": "60-95%",
  "scope_notes": "对杂芳基卤、位阻大的底物有额外注意事项"
}
```

molecule:
```json
{
  "label_en": "...",
  "role": "reactant|product|side_product|intermediate|reagent|catalyst|ligand|base|solvent|additive",
  "smiles": "...",
  "tags": ["role:catalyst", "metal:Pd", "oxidation_state:Pd(0)"]
}
```

mechanism_step:
```json
{
  "label_en": "...",
  "order": 1,
  "summary": "这一步在干什么",
  "key_bond_changes": "形成C-Pd / 断裂C-X",
  "tags": ["mechanism:oxidative_addition", "metal:Pd", "polarity:polar"]
}
```

side_pathway:
```json
{
  "label_en": "...",
  "summary": "竞争什么、典型副产物",
  "how_to_suppress": "抑制策略",
  "typical_side_products": ["异构化产物", "脱卤产物"],
  "tags": ["side:isomerization", "mechanism:beta_hydride_elimination"]
}
```

condition:
```json
{
  "label_en": "...",
  "param": "temperature|solvent|base|atmosphere|catalyst_loading|ligand|time|light|pressure|concentration|additive|acid",
  "value": "描述性取值",
  "tags": ["condition:solvent", "polarity:aprotic", "donor_number:high"]
}
```

total_synthesis_case:
```json
{
  "label_en": "...",
  "target_class": "alkaloid|polyketide|terpenoid|peptide|carbohydrate|polyene|natural_product",
  "key_reactions": ["Heck", "Sharpless epoxidation"],
  "strategy_tags": ["cascade", "ring-closing", "chiral_pool", "asymmetric_catalysis"],
  "tags": ["class:total_synthesis", "target_class:alkaloid", "strategy:cascade"],
  "summary": "一句话概述该全合成的策略亮点"
}
```

## tags Controlled Vocabulary（v2 核心）

所有 tags 使用 `namespace:value` 格式。一个实体可挂多个 tag（跨命名空间）。**子 agent 写入时只能使用下表中的值**；确需新值时先在本文件登记再使用。

### `class:` 反应大类
```
class:cross-coupling        偶联
class:carbonyl              羰基转化
class:substitution          取代
class:elimination           消除
class:oxidation             氧化
class:reduction             还原
class:rearrangement         重排
class:pericyclic            周环
class:cycloaddition         环加成
class:ch_activation         C-H活化
class:photoredox            光氧化还原
class:electrochem           电化学
class:organocatalysis       有机小分子催化
class:biocatalysis          生物催化
class:multicomponent        多组分
class:cascade               级联/串联
class:total_synthesis       全合成案例
class:radical               自由基
class:organometallic        有机金属
class:acid_base             酸碱
```

### `mechanism:` 机理类型
```
mechanism:SN1               单分子亲核取代
mechanism:SN2               双分子亲核取代
mechanism:E1                单分子消除
mechanism:E2                双分子消除
mechanism:E1cb              消除-共轭碱机理
mechanism:nucleophilic_addition  亲核加成
mechanism:electrophilic_addition 亲电加成
mechanism:nucleophilic_acyl_sub  亲核酰基取代
mechanism:oxidative_addition 氧化加成
mechanism:reductive_elimination 还原消除
mechanism:migratory_insertion 迁移插入
mechanism:beta_hydride_elimination β-氢消除
mechanism:transmetalation   转金属
mechanism:ligand_exchange   配体交换
mechanism:proton_transfer   质子转移
mechanism:hydride_transfer  氢负离子转移
mechanism:electron_transfer 电子转移
mechanism:radical_chain     自由基链式
mechanism:radical addition  自由基加成
mechanism:radical_substitution 自由基取代
mechanism:sigmatropic       σ迁移
mechanism:electrocyclic     电环化
mechanism:cheletropic       均面加成
mechanism:ene               Ene反应
mechanism:pericyclic        周环协同
mechanism:chelation_control 螯合控制
mechanism:ion_pair          离子对
mechanism:adjacent_group    邻基参与
mechanism:somopy             SOMO催化(enamine/iminium)
mechanism:hydrogen_atom_transfer 氢原子转移(HAT)
mechanism:single_electron_transfer 单电子转移(SET)
mechanism:proton_coupled_et 质子耦合电子转移(PCET)
mechanism:dyotropic         双向迁移
mechanism:metallacycle      金属环
mechanism:carbene_transfer  卡宾转移
mechanism:nitrene_transfer  氮宾转移
```

### `metal:` 催化金属中心
```
metal:Pd  metal:Ni  metal:Cu  metal:Rh  metal:Ir  metal:Ru
metal:Fe  metal:Co  metal:Mn  metal:Au  metal:Ag  metal:Zn
metal:Mg  metal:Li  metal:Na  metal:K   metal:B    metal:Si
metal:Al  metal:Sc  metal:Ti  metal:Zr  metal:Mo   metal:W
metal:Re  metal:Os  metal:Sn  metal:Pb  metal:Sb   metal:Bi
metal:Cr  metal:Ce  metal:In  metal:Ga
metal:none  （有机催化/无金属）
```

### `reactant_type:` 底物/试剂类型
```
reactant_type:aryl_halide       芳基卤
reactant_type:vinyl_halide      乙烯基卤
reactant_type:alkyl_halide      烷基卤
reactant_type:pseudohalide      拟卤（OTf, OTs, N2+等）
reactant_type:alkene            烯烃
reactant_type:alkyne            炔烃
reactant_type:allene            累积二烯
reactant_type:arene             芳环
reactant_type:heteroarene       杂芳环
reactant_type:aldehyde          醛
reactant_type:ketone            酮
reactant_type:ester             酯
reactant_type:amide             酰胺
reactant_type:acid              羧酸
reactant_type:acid_chloride     酰氯
reactant_type:anhydride         酸酐
reactant_type:nitrile           腈
reactant_type:imine             亚胺
reactant_type:enone             烯酮(共轭)
reactant_type:epoxide           环氧化物
reactant_type:aziridine         氮丙啶
reactant_type:alcohol           醇
reactant_type:amine             胺
reactant_type:thiol             硫醇
reactant_type:boronic_acid      硼酸
reactant_type:boronate          频哪醇硼酸酯
reactant_type:organozinc        有机锌
reactant_type:organoboron       有机硼
reactant_type:organosilane      有机硅
reactant_type:organotin         有机锡
reactant_type:grignard          格氏试剂
reactant_type:organolithium      有机锂
reactant_type:enol              烯醇
reactant_type:enolate           烯醇负离子
reactant_type:enamine           烯胺
reactant_type:diene             双烯
reactant_type:dienophile        亲双烯体
reactant_type:carbene           卡宾
reactant_type:carbenoid         类卡宾
reactant_type:nitrene           氮宾
reactant_type:radical_precursor 自由基前体(引发剂/光催化剂)
reactant_type:diazo             重氮化合物
reactant_type:azide             叠氮
reactant_type:isocyanate        异氰酸酯
reactant_type:phosphine         膦
reactant_type:NHC               NHC卡宾
```

### `bond_formed:` 成键类型
```
bond_formed:C-C  bond_formed:C-N  bond_formed:C-O  bond_formed:C-S
bond_formed:C-B  bond_formed:C-Si bond_formed:C-P  bond_formed:C-F
bond_formed:C-Cl bond_formed:C-Br bond_formed:C-I  bond_formed:C-H
bond_formed:C-metal  bond_formed:N-H  bond_formed:O-H  bond_formed:S-H
bond_formed:C-halogen  bond_formed:C-CN  bond_formed:C-CO  bond_formed:C-acyl
```

### `selectivity:` 选择性维度
```
selectivity:chemo     化学选择性
selectivity:regio     区域选择性
selectivity:stereo    立体选择性（顺反/相对构型）
selectivity:enantio   对映选择性
selectivity:diastereo 非对映选择性
selectivity:site      位点选择性（多官能团）
selectivity:size      大小环选择性
```

### `role:` 物种角色
```
role:catalyst  role:reagent  role:solvent  role:base  role:acid
role:ligand    role:additive role:oxidant  role:reductant  role:template
role:reactant  role:product  role:side_product  role:intermediate
```

### `condition:` 条件参数类型
```
condition:temperature  condition:solvent  condition:base  condition:acid
condition:atmosphere   condition:catalyst_loading  condition:ligand
condition:time         condition:light    condition:pressure
condition:concentration condition:additive  condition:order_of_addition
condition:technique    （微波/超声/流动/机械化学等）
```

### `polarity:` 介质极性/性质（用于 solvent 类）
```
polarity:protic  polarity:aprotic  polarity:polar  polarity:nonpolar
polarity:lewis_acidic  polarity:lewis_basic
```

### `frontier:` 前沿标记
```
frontier:true    近5年活跃/有重要突破
frontier:false   经典成熟方法
```

### `compchem:` 与计算化学的衔接（为后续联合检索预留）
```
compchem:barrier_prediction   能垒预测相关
compchem:ts_search            过渡态搜索相关
compchem:mechanism_study      机理计算研究
compchem:selectivity_model    选择性计算模型
compchem:solvent_effect       溶剂效应
compchem:redox_potential      氧化还原电位
compchem:excited_state        激发态相关
compchem:spectra_prediction   光谱预测
compchem:conformational       构象分析
```

### `strategy:` 合成策略（全合成用）
```
strategy:linear        线性合成
strategy:convergent    汇聚合成
strategy:ring_closing  关环策略
strategy:cascade       级联策略
strategy:chiral_pool   手性池
strategy:asymmetric_catalysis 不对称催化
strategy:biomimetic    生物仿生
strategy:diversity_oriented 定向多样性
strategy:protecting_group_free 无保护基
strategy:late_stage_functionalization后期官能团化
```

### `target_class:` 全合成目标类别
```
target_class:alkaloid     target_class:polyketide    target_class:terpenoid
target_class:peptide      target_class:carbohydrate  target_class:polyene
target_class:polyether    target_class:nucleoside    target_class:antibiotic
target_class:natural_product  target_class:unnatural
```

## 知识卡片（cards.jsonl）

每条机理/副反应写成 1–N 张卡片，字段对齐现有 `vector_store/cards.jsonl`：

```json
{"card_id": "org:<family>:<n>", "blog_id": "org", "file": "ORG-有机反应机理/<family>/<reaction>_卡片.md", "heading": "...", "content": "中文正文", "domain": "有机反应机理与副反应", "topic": "<反应名>", "fm_title": "<反应名>机理与副反应", "lang": "zh"}
```

英文卡 `"lang":"en"`，`card_id` 相同（中英对照）。

卡片 markdown 源文件放 `知识卡片/ORG-有机反应机理/<family>/`，frontmatter 与现有卡片一致：
```yaml
---
id: org:<family>:<n>
title: <反应中文名>
domain: 有机反应机理与副反应
topic: <反应英文名/主题>
cards: <卡数>
---
```

正文用 `## N. 小节标题` 分卡，每节对应 cards.jsonl 一行。

## 覆盖范围

### Phase 1（六族并行）
1. **coupling 偶联**：Heck, Suzuki, Sonogashira, Negishi, Kumada, Buchwald–Hartwig, Stille, Suzuki–Miyaura, Hiyama, Liebeskind–Srogl
2. **carbonyl 羰基**：Aldol, Claisen, Dieckmann, Wittig, HWE, Mukaiyama aldol, Grignard addition, Barbier, Reformatsky, Henry, Knoevenagel, Mannich, Baylis–Hillman
3. **sub_elim 取代/消除**：SN1, SN2, E1, E2, E1cb, 邻基参与, Fischer酯化, 酰胺化, 还原胺化
4. **ox_red 氧化/还原**：Swern, Dess–Martin, PCC/PDC, TPAP, NaBH4, LiAlH4, DIBAL, 催化氢化, Sharpless AD/Epoxidation, Jacobsen, CBS, 氧气氧化, DDQ
5. **rearrangement 重排**：Wagner–Meerwein, Beckmann, Curtius, Hofmann, Lossen, Schmidt, Claisen重排, Cope, oxy-Cope, Fries, benzilic, pinacol, semipinacol, Nametkin, Felkin–Anh 开环
6. **frontier 前沿**：C–H活化(Pd/Rh/Cu/Ni), 光氧化还原(Ir/Ru/有机染料), 电化学, MacMillan SOMO, NHC催化, 卡宾/氮宾, HAT催化, PCET, 光镍双催化, Fe/Co丰产金属催化

### Phase 2+（深挖+拓宽）
- 经典全合成案例（每案例一个 `total_synthesis_case` 实体 + `illustrates` 关系到 Phase 1 反应）
- 更多反应：Huisgen/Click, Diels–Alder, Wittig重排, Mitsunobu, Steglich, Yamaguchi, RCM/CM, Pd-π-allyl, 贝克曼重排, 亲核芳香取代(SNAr), 篱笆反应, Barton, 远程C-H官能团化
- 计算化学衔接卡片：哪些反应适合 DFT 机理研究、典型泛函/基组选择、溶剂模型、能垒参考值

## 每条主反应的最低内容要求

- 主机理链（≥3 步基元步骤，每步有 `mechanism_step` 实体与 `step_next` 关系）
- ≥1 条副路径（`side_pathway` 实体 + 典型副产物 SMILES + 抑制条件 `suppressed_by`）
- 关键条件实体（`requires` 关系，≥3 个：催化剂、碱/酸、温度、溶剂、气氛等）
- 完整 tags（class / mechanism / metal 或 none / bond_formed / reactant_type 至少覆盖）
- `compchem:` 至少一个衔接 tag

## 数据落地路径

| 产物 | 路径 | 说明 |
|---|---|---|
| 卡片 markdown | `知识卡片/ORG-有机反应机理/<family>/<reaction>_卡片.md` | 源文件 |
| 实体碎片 | `kg_data/organic/entities_<family>.csv` | 子 agent 写入 |
| 关系碎片 | `kg_data/organic/relations_<family>.csv` | 子 agent 写入 |
| 合并产物 | `kg_data/kg-entities.csv` / `kg-relations.csv` | 由 `scripts/kg_merge_organic.py` 原子合并 |
| cards.jsonl | `vector_store/cards.jsonl` | 由合并脚本追加（bilingual） |

**禁止子 agent 直接改主 kg-entities.csv / kg-relations.csv**；只写 `kg_data/organic/` 下的碎片，合并统一走脚本。

## source 字段约定

关系行的 `source` 列引用知识卡片 id：`org:<family>:<card_n>`。与计算化学的 `kb:NNN` 并存，后续检索可按前缀过滤域。
