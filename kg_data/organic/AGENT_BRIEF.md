# 有机知识库子 Agent 工作规范

你在为 Cloudra 的 chem-kb 搜集**有机反应机理与条件**知识。产出会被合并进现有计算化学知识图谱与向量检索。

## 必读

1. `kg_data/organic_schema.md` — schema v2 全文。**tags 只能用其中 controlled vocabulary 的值**；新值先在该文件登记再使用。
2. 本文余下部分 — 输出格式与质量红线。

## 你要产出什么（每族）

### A. 卡片 markdown

路径：`知识卡片/ORG-有机反应机理/<family>/<ReactionEnglishName>_卡片.md`

frontmatter：
```yaml
---
id: org:<family>:<1-based-seq>
title: <反应中文名>
domain: 有机反应机理与副反应
topic: <Reaction English Name>
cards: <小节数>
---
```

正文用 `## N. 小节标题` 分卡。每个主反应至少 6–10 张卡，建议结构：
1. 反应概览（发现历史、适用范围、典型产率）
2. 主机理链分步（每步一张卡，写清成断键、氧化态变化）
3. 关键条件与配体/碱/溶剂选择
4. 底物范围与局限
5. 副路径与抑制策略（≥1 条）
6. 选择性控制（chemo/regio/stereo/enantio）
7. 代表性应用或与计算化学的衔接（DFT 怎么算、典型方法学选择）
8. （若有）变体与最新进展

### B. 实体碎片 CSV

路径：`kg_data/organic/entities_<family>.csv`  
列：`id,type,label,smiles,props,n_sources`

- `id` 前缀与 type 对应（见 schema）
- `props` 是 JSON 字符串（CSV 里转义），**必须含 `tags` 数组与 `label_en`**
- SMILES 能写就写；写不出留空
- 每个主反应：1 个 `reaction` + ≥3 个 `mechanism_step` + ≥1 个 `side_pathway` + ≥3 个 `condition` + 关键 `molecule`（催化剂/典型底物/典型产物/副产物）

### C. 关系碎片 CSV

路径：`kg_data/organic/relations_<family>.csv`  
列：`src_id,dst_id,rel_type,evidence_level,source,falsified,note`

- `source` 列 = `org:<family>:<card_seq>`（引用卡片）
- `evidence_level` 默认 `L0`
- `falsified` 填 `false`
- `note` 写一句中文说明
- 确保：每个 reaction `proceeds_via` 其 steps；steps 间 `step_next`；reaction `requires` conditions；side_pathway `competes_with` reaction 且 `suppressed_by` condition；reaction `produces` products；`applies_to` functional_groups；至少一个 `relevant_to_compchem` 指向计算化学概念（若知道 id）否则跳过

### D. 可选：全合成案例

若有非常经典的案例与本族反应强相关，可在 `total_synthesis` family 里加一张卡 + `total_synthesis_case` 实体 + `illustrates` 关系。Phase 1 不强制。

## 质量红线

- **机理步骤的化学必须正确**。不确定的写 L0 教科书共识，不要编造过渡态结构或能垒数值。
- 每个副路径必须给出**可操作的抑制条件**。
- 卡片正文用**中文**；`label_en`/英文卡可选（Phase 1 以中文为主，英文卡 Phase 2 补）。
- 禁止正则思维：tags 用词表精确值，不要自造近义词。
- 卡片内容应足够独立可检索（单卡读懂一个要点，不依赖上下文）。

## 研究方法

- **本环境 websearch 插件不可用**。改用 `webfetch` 拉 Wikipedia / 公开综述页补细节；拉不到就按教科书共识写（Clayden / Carey / March / 知名 review 的公开描述）。
- **不要编造文献卷号页码**；引用只写「综述见 Chem. Rev. 过渡金属催化偶联专号」这类模糊指向。
- 每族预算：webfetch 4–10 次，覆盖主反应的关键点即可，不要陷入单个反应写三天。

## 写入纪律

- **只写** `kg_data/organic/` 与 `知识卡片/ORG-有机反应机理/<family>/` 下的文件。
- **绝不修改**主 `kg-entities.csv` / `kg-relations.csv` / `cards.jsonl` / 其他族的文件。
- CSV 用 UTF-8（无 BOM），逗号分隔，props 内逗号注意转义（推荐用 Python csv 模块生成）。
- 同族内 id 不得重复；跨族 id 前缀不同自然隔离。
- 完成后跑：`python3 scripts/kg_merge_organic.py --check -v` 确认你的碎片无悬挂引用与非法 tag（只校验不写主表）。

### relevant_to_compchem 关系

指向计算化学主实体（如 `concept:过渡态`）的 `relevant_to_compchem` 关系**允许 dst 不在有机碎片表**（校验脚本已放行）。dst id 需是主 KG 中真实存在的计算化学实体 id；不确定就跳过该关系，不要瞎编 id。

### 已知坑（Phase 1 经验）

- Stille 用有机锡：tags 加 `metal:Sn`（已入词表）。
- `oxidation_state:Pd(0)` 等开放命名空间不校验具体值，可自由使用。
- 副路径细分类用 `side:` 开放命名空间。

## 产出规模参考（每族）

| 族 | 主反应数 | 实体约 | 关系约 | 卡片 md 文件 |
|---|---|---|---|---|
| coupling | 8–10 | 150–250 | 200–350 | 8–10 |
| carbonyl | 10–12 | 180–300 | 250–400 | 10–12 |
| sub_elim | 6–8 | 120–200 | 180–280 | 6–8 |
| ox_red | 10–12 | 160–260 | 220–360 | 10–12 |
| rearrangement | 10–12 | 160–260 | 220–360 | 10–12 |
| frontier | 8–10 | 140–240 | 200–340 | 8–10 |

宁可少而准：写 8 个反应 × 10 张卡 + 完整实体关系，好过 15 个反应都是空壳。
