# 知识库标签体系与分面检索（v13）

chem-kb 知识库的多维标签系统：给 8,594 张知识卡片按 **方法 / 软件 / 问题种类 / 报错类型** 四个维度打受控标签（体系维度 `domain` 继承源目录字段），并把标签贯通到向量服务、图谱、混合 provider 与自动注入的整条检索链路。词表是**人工维护的受控配置**，打标是 **LLM 批量标注**，两者分离可独立演进。

## 一、词表：`vector_store/tag_vocab.yaml`

五个 facet（维度）：

| facet | 值数 | 来源 | 用途 |
| --- | --- | --- | --- |
| `domain` | 10 | 继承 cards.jsonl 既有字段（与源目录 1:1，中英双语） | 一级体系分类，**不经 LLM** |
| `method` | 25 | KG method/software 实体（n_sources≥3）人工筛选 | DFT/MP2/溶剂模型/QTAIM/MD… |
| `software` | 18 | 同上 | Gaussian/Multiwfn/ORCA/GROMACS… |
| `problem` | 19 | 新建受控词表 | SCF不收敛/虚频/过渡态/基组选择/内存并行… |
| `error` | 18 | 报错签名挖掘（活跃语料 + **归档区仅挖词**） | L502/galloc/PGFIO/Erroneous wavefunction… |

每个条目：`id`（ASCII snake_case，入库值）/ `label`（中文展示名）/ `aliases`（别名与同义词，LLM prompt 与查询侧确定性匹配共用）。`error` 条目另带 `source: active|archive|manual` 溯源。

要点：

- **归档区护栏**：`知识卡片/_ARCHIVE_NOTICE.md` 禁止归档区作为管线输入。v13 只从归档区**挖掘报错签名词表**（"错误提示：XXX" 标题等 verbatim 原文），卡片库仍只用活跃区 01–10 目录。挖掘脚本：`scripts/tag_vocab_mine.py`。
- **词表生长闭环**：LLM 提议的词表外 tag 不落库，聚合写入 `vector_store/_tag_state/pending_tags.json`，人工审核后手工补进 YAML（改完无需重启检索——provider 在进程内缓存词表，重启 uvicorn 生效）。
- 列出词表：`cloudra knowledge tags [--facet error]`。

## 二、打标流水线：`cloudra knowledge tag build`

实现：`cloudra/knowledge/tagging.py`（LLM 传输复用 `cloudra.infra.llm_client`，provider 取 `config.coordinator`，可被参数覆盖）。

```bash
uv run cloudra knowledge tag build                 # 全量（约 8.6k 卡 ≈ 570 批）
uv run cloudra knowledge tag build --limit 100     # 先打 100 张试效果
uv run cloudra knowledge tag build --dry-run       # 只调 LLM 出报告，不写盘
uv run cloudra knowledge tag build --refresh       # 忽略缓存全部重打
```

行为与保证：

1. **批量约束输出**：每批 15 卡（heading + 正文截 600 字符），prompt 携带完整词表枚举，输出必须为词表 id——词表外进 pending，不污染数据。
2. **断点幂等**：缓存键 = sha1(card_id|heading|content)，存 `vector_store/_tag_state/tag_cache.jsonl`。重跑只调新卡/内容变过的卡，其余走缓存零成本。
3. **行对齐写回**：tags 字段原位写进 cards.jsonl，**行数与顺序严格不变**——`vectors.f16.npy` 按行对齐，因此**无需重编码向量库**（tags 是检索期元数据，不进向量）。
4. zh/en 双行共享同一份 tags（同卡同标签）。
5. LLM 失败的批次记录在报告中，重跑自动补；并发 4 路限幅。

覆盖率检查：`cloudra knowledge tag stats`（卡片侧覆盖率 + 各维度 top 标签 + 图谱侧分布）。

## 三、实体侧反贴：`cloudra knowledge tag apply-db`

卡片 tags 通过 `kg_relations.source`（`kb:422` / `kb:dyn01` 博客级指针）反贴到关系两端的实体，存入 `chem_kg.db` 的派生表 `kg_entity_tags`：

```bash
uv run cloudra knowledge import     # 1. 建库（幂等）
uv run cloudra knowledge tag build  # 2. 卡片打标
uv run cloudra knowledge tag apply-db  # 3. 反贴到实体（整表重建，幂等）
```

上游 `kg_data/*.csv` 是外部抽取管线的产物，**不做任何改动**——`kg_entity_tags` 是纯派生数据，可随时从 cards.jsonl 重建。实体标签自动进图谱条目返回值，`note` 因果解释（如"使用%oldchk可避免过渡态文件TS.chk被改写"）也从此拼进图谱条目 content（`‖` 分隔，≤200 码点）。

## 四、检索链路如何使用标签

### 1. 报错优先路由（`knowledge/plugin.py`）

查询文本先经词表 aliases 做**确定性报错签名检测**（只认 verbatim 程序输出，宁漏勿误）。命中时语义通道带 `tags={"error":[...]}` 过滤、图谱通道带 `facets={"error":[...]}` 过滤；过滤为空则自动回退无过滤——词表缺失或打标未跑时行为与 v12 完全一致，优雅降级。配额矩阵（3 语义 + 2 图谱）与降级矩阵不变。

### 2. 向量服务（`scripts/kg_vec_service.py`）

`POST /search` 新增可选字段：`domain`（str 或 list，精确匹配）、`tags`（扁平 list = 任一命中；dict = facet 间 AND、facet 内任一）。过滤是 top-k 后过滤（扫完整排序直到凑满 k），**过滤后不足 k 条不会用不相关行凑数**。响应每条 hit 携带 `tags`。

### 3. 查询构造（`runtime_v2/policies/knowledge_stage.py`）

自动注入的查询从"工具名+全部参数+summary 全文"（≤800 字符 blob，FTS 全 token AND 命中率≈0——图谱/模糊通道实际失效的根源）改为：**工具名 + 短参数（SMILES/方法名/短路径；>120 字符与纯数字丢弃）+ summary 报错窗口，≤200 字符**。

### 4. 注入分级

- `is_success=False`（工具失败）：**必注入**——排障价值最高，且失败路径的查询本身短而准。
- 成功：仅当 top 命中分 ≥ `_SUCCESS_SCORE_THRESHOLD`（0.55，模块常量可调）才注入——压掉"每次计算都注入"的上下文噪声，对齐验证计划"被动提示仅在关键节点触发"原则。

### 5. 面向 agent 的可见性

命中条目携带受控 tags，渲染形如：

```
- [L0] [tags: err_l502|scf_not_converged] 〔卡片〕SCF不收敛的解决策略: … (provider: chem-kb) — source: kb:164
```

英文查询自动传 `lang=en` 给语义通道（v11 的 ASCII≥70% 启发复用）。

## 五、分面检索入口

```bash
# 图谱 CLI：标签/类型过滤（tag 格式 facet:tag_id，可多次）
uv run cloudra knowledge search "不收敛" --tag error:err_l502 --type pitfall

# HTTP API（tag 可重复；裸 tag_id 按 error 惯例处理）
GET /api/v2/knowledge/search?q=过渡态&tag=problem:ts_search&tag=error:err_l9999&type=concept

# 向量服务直查（调试）
curl -s 127.0.0.1:8765/search -H 'Content-Type: application/json' \
  -d '{"query":"SCF不收敛","k":5,"tags":{"error":["err_l502"]}}'
```

## 六、维护手册

| 场景 | 操作 |
| --- | --- |
| 词表加新值 | 编辑 `tag_vocab.yaml` → 重启 uvicorn → `tag build`（新值只影响后续打标；已打卡片不受影响） |
| 打标效果差 | 看 `tag stats` 覆盖率与 top 标签；改 prompt（`tagging._SYSTEM_PROMPT`）或词表 aliases 后 `--refresh` 重打 |
| 换 LLM | `tag build --model … --url … --key …` 或改 `config.coordinator` |
| 卡片库更新 | 追加 cards.jsonl（保持行序，**只追加不中间插行**——向量按行对齐）→ `encode.py` 重编码 → `tag build`（只打新卡）→ `apply-db` |
| 审核 pending | 看 `vector_store/_tag_state/pending_tags.json`（facet:value → 计数），值得保留的手工补进词表 |

## 七、测试

`tests/test_knowledge_tagging.py`：词表良构、报错签名检测（含防误报）、zh/en 分组、LLM 输出校验、写回行对齐、缓存断点、dry-run 零写盘、假 LLM 端到端、source 映射与 store 反贴/分面检索集成。
