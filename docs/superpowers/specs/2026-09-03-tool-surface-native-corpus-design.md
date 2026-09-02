# 工具表面：贴合模型语料的合并与改名

> 状态：待评审。评审通过前不进入实现。
> 动机：模型经常把工具名填错。根因是日常 I/O 把 Python 类名当成 function name，且近义工具拆得过碎。

## Goal

把模型每次都会用的读写/检索入口改成它训练里见过的动词，并把「同一用户意图、只是介质或后端不同」的工具并成一个入口。同一批改掉会正面打架的线名。不考虑向后兼容：旧线名从 registry 删除，调用时只提示新名，不执行别名。

## Out of scope

- 不合并 `dag_*`、化学计算链、`todo_*`、`email_*`、`query_compute_*`、`ask_user`、`stop`、`schedule`（`schedule` 只修正 prompt 里写错的参数名）。
- 不合并 `web_fetch` 与 `browser`（静态抓取 vs JS 浏览器）。
- 不合并 `write` 与 `edit`。
- 不改 `image_to_smiles`（化学识别，不是打开文件）。
- 不把 `SubAgentLauncher` 的 `query` 改成 `prompt`。
- 不重命名 `Searchtool` / `Bashtool` 等包目录。
- 不改供应商协议里的原生 `web_search`（DeepSeek/OpenAI 的名字，见 `llm_client.py`）。
- 不重放或改写历史事件里的旧 `tool_name`。

## 1. 线名表

### 并掉（旧线名删除）

| 旧 | 新 |
|---|---|
| `text_reader`、`image_reader`、`pdf2md`、`pdf2image` | `read` |
| `web_search`、`paper_searcher`、`openalex_searcher` | `search` |

### 只改名

| 旧 | 新 |
|---|---|
| `bashtools` | `bash` |
| `text_writer` | `write` |
| `edit_file` | `edit` |
| `getskill` | `get_skill` |
| `web_fetcher` | `web_fetch` |
| `headless_browser` | `browser` |
| `SubAgentLauncher` | `subagent_launcher` |
| `SubAgentSwarm` | `subagent_swarm` |

实现收到内部函数，registry 不再挂旧名。

## 2. `read`

按路径分流，不让模型选「读哪种文件」。

### 参数

| 参数 | 含义 |
|---|---|
| `path` | 工作区相对路径。不用 `filepath` / `image_path` / 绝对路径。 |
| `offset` | 可选，从 1 起的起始行。省略则从头。 |
| `limit` | 可选，读多少行。省略则到文件末尾。 |
| `focus` | 仅文档有意义：`auto`（默认）/ `text` / `images`。 |

`offset` / `limit` 是调用方窗口，也是缩小返回的**唯一**合法方式。

### 分流

- **文本**（代码、log、抽出的 md）：返回切片 + 全文件 `sha256`（给后续 `edit` / `write`）。
- **图**（png/jpg/jpeg/webp）：交给视觉回注。`read` 始终出现在工具列表里，不靠藏工具做 visual 开关；没开 visual 或模型无视觉时，只返回路径 + 一句说明。
- **PDF**：走文档分支（见下）。`pdf2md` 描述写过 Word/Excel/PPT，实现只开 PDF；`.docx` 等明确报错，不假装会转。
- 其它二进制：失败并说明。

### PDF

抽到 `.cloudra/extract/<源文件 sha256 前 16 位>/`（harness 缓存，与 `.cloudra/tool_output/` 同类，**不**占 WRITE/SCRIPT）。源文件变了则缓存失效重抽。对同一 PDF 再 `read` 且带 `offset`/`limit`，分页的是抽出的正文，不必先记住缓存路径。

扫描件判定：抽出正文按页均不足约 50 字，或全文 < 200 字，视为无文字层。

| `focus` | 有文字层 | 扫描件（无文字层） |
|---|---|---|
| `auto`（默认） | 正文 + **完整**图清单（路径/页码）。图不回注。 | 每一页都渲染进缓存，清单给全，视觉开着则**全部回注**。 |
| `text` | 只要正文，不列图。 | 只说明没有文字层，不改成给图。 |
| `images` | 只要图：先嵌入图（全给），没有再整页渲染（全给）。 | 与 `auto` 相同：全页渲染、全清单、全回注。 |

要看某张图：再 `read` 清单里的路径，和读一张普通 png 同一条工具。

### 禁止无法控制的截断

- 不得静默丢页、丢图、或「最多回注 N 页」。
- `read` 内部不得再做 30k 字符静默截断。
- 未传 `offset`/`limit` 时返回该 `focus` 下的完整结果。
- 观察值太大走现有 `.cloudra/tool_output/` 落盘：全文仍在，路径写进结果，并写明用 `offset`/`limit` 再读。这不是「读完了」，也不是丢弃。

视觉回注认 `image_path` 或 `image_paths`（张数不封顶）。`pymol_render` 仍走 `visual=True` 整工具隐藏。

### 权限

`is_read()`。explorer 可以直接读论文。

## 3. `search`

| 参数 | 含义 |
|---|---|
| `query` | 检索词（必填） |
| `source` | `web` / `arxiv` / `openalex`，默认 `web` |
| `max_results` | 条数，默认 8 |
| `mode` | `light` / `normal` / `weight`，默认 `normal`。`source=web` 时忽略。 |

`sort_by` / `page` / `backend` 不暴露，内部用现在的默认。三个旧后端变成内部函数。

### 原生联网搜索

今天按函数名丢掉整个 `web_search`。并成 `search` 后不能整工具丢掉，否则 arXiv/OpenAlex 没了。

原生搜索开着时：**当场改 schema**，`source` 只剩 `arxiv|openalex`，默认改为 `arxiv`，描述写明 web 已由模型端提供。若仍传 `source=web`，工具返回错误，不再搜一遍。`llm_client.py` 里供应商协议的 `web_search` 不动。

## 4. 只改名的工具（参数）

| 新线名 | 参数 |
|---|---|
| `bash` | 仍是 `command`。`task_description` 留给 UI/审批。compute predicate 从 `bashtools` 继承。 |
| `write` | `filepath` → `path`；`content`、`expected_sha256` 不动。 |
| `edit` | 同样 `path`。`edits[]` 保留。schema 主名 `old_string` / `new_string`，仍接受 `old_str` / `old_text`。 |
| `get_skill` | `other` → `reference`。 |
| `web_fetch` | `url` 不动。 |
| `browser` | `url` + `action=fetch\|screenshot` 不动。 |
| `subagent_launcher` / `subagent_swarm` | 只改线名。`query` / `prompt_template` 不动。 |

顺手改 prompt 撒谎：`schedule` 真实字段是 `delay_seconds` + `message`。把 `DurationSeconds` / `Prompt` 从 `schedule_stage` 和角色 prompt（`dft.md`、`small_mol.md` 等）改掉。

## 5. 未知工具：只提示，不执行

旧线名从 registry 删除。`adapters.py` 现有 `unknown tool` 分支加显式映射表，返回一句指向新名的提示。不模糊执行、不留 alias 回退。

| 调用 | 提示指向 |
|---|---|
| `text_reader` / `image_reader` / `pdf2md` / `pdf2image` / `read_file` | `read` |
| `web_search` / `paper_searcher` / `openalex_searcher` | `search`（可补 `source=`） |
| `bashtools` / `shell` | `bash` |
| `text_writer` / `write_file` | `write` |
| `edit_file` / `str_replace` | `edit` |
| `getskill` | `get_skill` |
| `web_fetcher` | `web_fetch` |
| `headless_browser` | `browser` |
| `SubAgentLauncher` | `subagent_launcher` |
| `SubAgentSwarm` | `subagent_swarm` |

## 6. 权限 / visual / 平台 / DAG

- `read` **不**进 `visual_tools()`。图是否回注仍看 `visual_mode × supports_vision`。
- `runtime_profiles` 跟随改名前的条目，只换名字、不扩大平台（`bash` / `browser` 仍是 desktop-only；`read` / `search` / `web_fetch` / `write` / `edit` / `get_skill` 跟原 android 白名单走）。
- DAG：`bash` 继承现在 `bashtools` 的 compute predicate；`read` / `search` 不是 compute entry。
- `subagent_bridge` 拦截名改成 `subagent_launcher` / `subagent_swarm`。
- `dag_stage` 里写死的 `SubAgentLauncher` / `SubAgentSwarm` 跟着改。

## 7. 代码怎么拆

包目录不改。线名对应的模块改名，旧 Tool 类删除：

- 新入口：`cloudra/tools/Searchtool/read.py`、`cloudra/tools/Searchtool/search.py`
- 抽出的实现变成私有模块，不再注册：`_text.py`、`_image.py`、`_document.py`、`_web.py`、`_arxiv.py`、`_openalex.py`
- 1:1 改名：`bashtools.py` → `bash.py`（类 `Bash`），`text_writer.py` → `write.py`，`edit_file.py` → `edit.py`，`web_fetcher.py` → `web_fetch.py`，`headless_browser.py` → `browser.py`
- `get_skill.py` / `subagent_*.py` 文件名已对，只改 `tool_name`

registry、capabilities、prompts、skills、交叉 description、`AGENTS.md` 全部改成新名。

前端 `timeline.ts`：**展示**时新旧名都认（历史事件里还是 `text_reader`）。这不是运行时别名，不改旧事件。

## 8. 测试（先红后绿）

新测把问题测红，再改实现：

- registry 里没有旧线名；有 `read` / `search` / `bash` / `write` / `edit` / `get_skill` / `web_fetch` / `browser` / `subagent_launcher` / `subagent_swarm`
- `read`：文本切片 + sha256；png 走视觉字段；PDF auto 给正文+完整图清单且不回注图；扫描件清单与回注都是全页，无 N 页上限；未传 `offset`/`limit` 时正文不被 30k 截断；缓存命中；explorer 能读 PDF；`.docx` 报错
- `search`：默认 web；`source=arxiv|openalex` 分发；`mode` 在 web 下忽略；原生搜索开启时 schema 去掉 `web`，传入 `source=web` 失败
- 未知名 `text_reader` / `web_search` / `bashtools` 返回提示、不执行
- `edit` 接受 `old_string`；`write` / `read` / `edit` 都用 `path`
- `get_skill` 字段只有 `reference`；传入 `other` 因 `additionalProperties: false` 被拒

旧测试里写死的线名跟着改（至少：`test_workspace`、`test_web_search*`、`test_paper_searcher`、`test_openalex_searcher`、`test_benchmark` 的 `bashtools`、`test_runtime_v2_subagent_bridge`、`test_yolo_guard`、`test_prompt_assembler`、`test_coord_guard`、`test_tool_semantics`、`test_tools_core`、`test_runtime_v2_visual_mode`、`frontend/src/timeline.test.ts`）。不留「旧名仍可用」的测试。
