# 知识库标签维护与显式分面检索

知识卡片按 **方法 / 软件 / 问题种类 / 报错类型** 四个维度打受控标签，`domain` 继承源目录字段。词表人工维护，打标由 LLM 批量完成。标签/类型筛选由维护者通过 CLI、图谱 HTTP API 或独立向量脚本显式使用；在线 AgentHub 用图谱关键词索引返回同源完整抽取整理稿，不做自动报错路由，工具完成或失败也不会触发检索。

## 一、词表：`vector_store/tag_vocab.yaml`

五个 facet（维度）：

| facet | 值数 | 来源 | 用途 |
| --- | --- | --- | --- |
| `domain` | 10 | 继承 cards.jsonl 既有字段（与源目录 1:1，中英双语） | 一级体系分类，**不经 LLM** |
| `method` | 25 | KG method/software 实体（n_sources≥3）人工筛选 | DFT/MP2/溶剂模型/QTAIM/MD… |
| `software` | 18 | 同上 | Gaussian/Multiwfn/ORCA/GROMACS… |
| `problem` | 19 | 新建受控词表 | SCF不收敛/虚频/过渡态/基组选择/内存并行… |
| `error` | 18 | 报错签名挖掘（活跃语料 + **归档区仅挖词**） | L502/galloc/PGFIO/Erroneous wavefunction… |

每个条目：`id`（ASCII snake_case，入库值）/ `label`（中文展示名）/ `aliases`（别名与同义词，供打标提示与人工维护参考）。`error` 条目另带 `source: active|archive|manual` 溯源。

要点：

- **归档区护栏**：`知识卡片/_ARCHIVE_NOTICE.md` 禁止归档区作为管线输入。v13 只从归档区**挖掘报错签名词表**（"错误提示：XXX" 标题等 verbatim 原文），卡片库仍只用活跃区 01–10 目录。挖掘脚本：`scripts/tag_vocab_mine.py`。
- **词表生长闭环**：LLM 提议的词表外 tag 不落库，聚合写入 `vector_store/_tag_state/pending_tags.json`，人工审核后手工补进 YAML。修改词表后在下次打标命令中读取；已有卡片标签需要重打才会改变。
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

卡片 tags 通过 `kg_relations.source`（`kb:422` / `kb:dyn01` 来源级指针）反贴到关系两端的实体，存入 `chem_kg.db` 的派生表 `kg_entity_tags`：

```bash
uv run cloudra knowledge import     # 1. 建库（幂等）
uv run cloudra knowledge tag build  # 2. 卡片打标
uv run cloudra knowledge tag apply-db  # 3. 反贴到实体（整表重建，幂等）
```

上游 `kg_data/*.csv` 是外部抽取管线的产物，**不做任何改动**——`kg_entity_tags` 是纯派生数据，可随时从 cards.jsonl 重建。这些标签用于图谱显式分面检索。在线插件按来源返回完整抽取整理稿，不再把实体及关系 `note` 拼成短摘要。

## 四、在线查询与独立向量脚本

chem-kb 的启停使用 `cloudra knowledge install` / `cloudra knowledge uninstall`，重启 Cloudra 服务后生效；关闭不影响 AgentHub 的其他能力。详见 [知识检索开关](PLUGINS.md#知识检索开关)。

Agent 遇到具体知识缺口时，加载 `get_skill(skill_name='knowledge-search')`，再调用 `agent_hub(action='search', keyword='Gaussian SCF')`。图谱直接命中的实体决定来源，再读取该来源的全部小节；每节选择查询语言版本，缺失时回退中文。`kb:` 是来源指针，不代表原文 URL；抽取整理稿不等同科学验收证据。

在线插件不识别报错 aliases 来自动过滤，不分配语义/图谱配额，也不调用向量服务补位。没有图谱命中或缺库时，返回空结果。

`scripts/kg_vec_service.py` 保留为独立手动语义检索工具。其 `POST /search` 支持可选 `domain`（字符串或列表，精确匹配）和 `tags`（扁平列表表示任一命中；字典表示维度间 AND、维度内任一）。筛选后不足 `k` 条不会用不相关行凑数。可选 `lang=zh|en` 限制语言；未指定时双语同卡去重。此服务不参与 AgentHub 的在线 chem-kb 查询。

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
| 词表加新值 | 编辑 `tag_vocab.yaml` → `tag build`（新值只影响后续打标；已有卡片要用 `--refresh` 重打） |
| 打标效果差 | 看 `tag stats` 覆盖率与 top 标签；改 prompt（`tagging._SYSTEM_PROMPT`）或词表 aliases 后 `--refresh` 重打 |
| 换 LLM | `tag build --model … --url … --key …` 或改 `config.coordinator` |
| 卡片库更新 | 更新 cards.jsonl → `tag build` → `apply-db`；仅使用独立向量脚本时，保持原行序并用 `encode.py` 重编码相应向量 |
| 审核 pending | 看 `vector_store/_tag_state/pending_tags.json`（facet:value → 计数），值得保留的手工补进词表 |

## 七、测试

`tests/test_knowledge_tagging.py`：词表良构、报错签名检测（含防误报）、zh/en 分组、LLM 输出校验、写回行对齐、缓存断点、dry-run 零写盘、假 LLM 端到端、source 映射与 store 反贴/分面检索集成。
