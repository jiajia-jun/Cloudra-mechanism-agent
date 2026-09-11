# 有机知识库构建进度

## 当前阶段

**Phase 1** ✅ 已完成并合并主表

| Agent | family | 实体 | 关系 | 卡片文件 | 状态 |
|---|---|---|---|---|---|
| general-1 | coupling | 133 | 250 | 10 | ✅ |
| general-2 | carbonyl | 217 | 368 | 12 | ✅ |
| general-3 | sub_elim | 197 | 307 | 12 | ✅ |
| general-4 | ox_red | 251 | 332 | 16 | ✅ |
| general-5 | rearrangement | 183 | 273 | 19 | ✅ |
| general-6 | frontier | 180 | 305 | 10 | ✅ |

**Phase 1 合并结果**（2026-08-31）：
- 主表 entities: 14203 → **15355**（+1152 org）
- 主表 relations: 10266 → **12101**（+1835 org）
- cards.jsonl: 17188 → **17836**（+648 org 行）
- 类型分布：reaction 82 / mechanism_step 280 / side_pathway 165 / condition 251 / molecule 309 / functional_group 65

**Phase 2** 🔄 进行中

| Agent | 任务 | 状态 |
|---|---|---|
| general-7 | total_synthesis 经典全合成案例 | 🔄 |
| general-8 | extra 补缺重要反应（DA/Click/RCM 等） | 🔄 |
| general-9 | compchem_bridge 计算化学衔接深挖 | 🔄 |

## Phase 1 已知 reaction id

### coupling
```
reaction:Heck_reaction
reaction:Suzuki-Miyaura_coupling
reaction:Sonogashira_coupling
reaction:Negishi_coupling
reaction:Kumada_coupling
reaction:Buchwald-Hartwig_amination
reaction:Stille_coupling
reaction:Hiyama_coupling
reaction:Liebeskind-Srogl_coupling
reaction:Fujiwara-Moritani_reaction
```

### carbonyl
```
reaction:Aldol addition
reaction:Mukaiyama aldol
reaction:Directed aldol
reaction:Claisen condensation
reaction:Dieckmann condensation
reaction:Wittig reaction
reaction:Horner-Wadsworth-Emmons reaction
reaction:Grignard addition
reaction:Barbier reaction
reaction:Reformatsky reaction
reaction:Henry reaction
reaction:Knoevenagel condensation
reaction:Mannich reaction
reaction:Baylis-Hillman reaction
reaction:Acyloin condensation
```

### sub_elim
```
reaction:SN1
reaction:SN2
reaction:E1
reaction:E2
reaction:E1cb
reaction:Anchimeric_Assistance
reaction:Fischer_Esterification_Amidation
reaction:Amide_Coupling
reaction:Reductive_Amination
reaction:Mitsunobu
reaction:SNAr
reaction:Nucleophilic_Acyl_Substitution
```

### ox_red
```
reaction:Swern oxidation
reaction:Dess-Martin oxidation
reaction:PCC-PDC oxidation
reaction:TPAP-NMO oxidation
reaction:Luche reduction
reaction:LiAlH4 reduction
reaction:DIBAL reduction
reaction:Catalytic hydrogenation
reaction:Transfer hydrogenation
reaction:Sharpless asymmetric dihydroxylation
reaction:Sharpless epoxidation
reaction:Jacobsen epoxidation
reaction:CBS reduction
reaction:DDQ oxidation
reaction:Wacker oxidation
reaction:Autoxidation
```

### rearrangement
```
reaction:Wagner-Meerwein rearrangement
reaction:Beckmann rearrangement
reaction:Curtius rearrangement
reaction:Hofmann rearrangement
reaction:Lossen rearrangement
reaction:Schmidt reaction
reaction:Claisen rearrangement
reaction:Cope rearrangement
reaction:oxy-Cope rearrangement
reaction:anionic oxy-Cope rearrangement
reaction:Fries rearrangement
reaction:benzilic acid rearrangement
reaction:pinacol rearrangement
reaction:semipinacol rearrangement
reaction:Nametkin rearrangement
reaction:demjanov rearrangement
reaction:Tiffeneau-Demjanov rearrangement
reaction:[2,3]-Wittig rearrangement
reaction:Wolff rearrangement
```

### frontier
```
reaction:Directed_Pd_CH_activation
reaction:Photoredox_catalysis
reaction:Dual_photoredox_Ni_coupling
reaction:Organic_electrosynthesis
reaction:SOMO_catalysis
reaction:NHC_organocatalysis
reaction:Metal_carbene_nitrene_transfer
reaction:HAT_catalysis
reaction:PCET_activation
reaction:Abundant_metal_cross_coupling
```

## 基础设施

- schema: `kg_data/organic_schema.md` v2（tags controlled vocabulary，metal 含 Na/K/Cr/Ce/In/Ga/Sn/Pb/Sb/Bi）
- 合并脚本: `scripts/kg_merge_organic.py`（--check / 默认合并 / --cards；跨族重复实体首定义优先；relevant_to_compchem 可指向主表实体）
- 子 agent 规范: `kg_data/organic/AGENT_BRIEF.md`
- 碎片目录: `kg_data/organic/entities_*.csv` + `relations_*.csv`
- 卡片目录: `知识卡片/ORG-有机反应机理/<family>/`
- 统计: `kg_data/organic/organic-stats.json`

## 经验教训

1. websearch 插件在子 agent 环境不可用 → webfetch Wikipedia + 教科书兜底
2. relevant_to_compchem 的 dst 允许指向主 KG 实体（校验已放行，carbonyl 写了 24 条）
3. metal 词表已扩充：Na/K/Cr/Ce/In/Ga/Sn/Pb/Sb/Bi
4. 跨族共享 functional_group:*/molecule:* 只定义一次，合并脚本首定义优先
5. 子 agent 用 Python csv 模块生成 CSV
6. Phase 1 规模：82 反应 → 1152 实体 / 1835 关系 / 648 卡片行，质量达标

## Phase 3+ 待做（Phase 2 完成后）

- 中英双语卡片补齐（当前仅 zh）
- 向量重编码（vector_store/encode.py，需 bge-m3 环境）
- 与计算化学实体的自动对齐（relevant_to_compchem 扩展）
- 更多前沿：生物催化、电化学变体、机器学习逆合成
- 副反应深度：每个主反应加 more side pathways
