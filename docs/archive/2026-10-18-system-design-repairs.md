# 系统体检修复记录（2026-10-18）

本轮落实[系统体检](2026-10-18-system-design-audit.md)确认的十五项工程修复，同时包含已经确认的两项 IRC 工程修复。按用户要求直接修复首个 Benchmark 问题：原生日志超过扫描大小不能被判成缺少科学证据。空图得分属于评分决策，保持现状。

本记录说明本地源码修改及验证结果；没有重启服务、部署新代码、提交新量化计算或取消真实作业。工作区中另外完成的、已经得到用户明确确认的 IB9 Gold 回填随全部改动一起交付，科学边界单列在后文。

## 已修复的工程问题

| 原问题 | 当前行为 | 回归覆盖 |
| --- | --- | --- |
| 远端取消请求被当作进程已退出 | SSH 使用现有执行端取消标记及所属进程组收尾；Slurm 检查取消结果并等待真实终态。传输异常、查不到账和进程尚存不释放容量；终态作业不重投 | `test_remote_compute`、`test_shell_remote_compute`、`test_slurm` |
| 角色 deny 没有进入真实工具集合 | 目录展示和执行使用同一个已扣除 deny 的能力集合 | `test_runtime_v2_design_repairs`、工具目录及权限测试 |
| 启动数据库 B 时复用数据库 A 的健康页面 | 先解析目标数据目录，再按现有 store 锁核对真实属主；端口冲突明确报出 | `test_web_launcher`、store 所有权测试 |
| 共享记忆压缩覆盖并发写入 | 模型返回后在同一路径锁内重读，保留压缩等待期间追加的内容；过时压缩结果不覆盖较新压缩 | `test_memory_concurrency`、`test_memory_scope_guard` |
| 提供的完整三维几何被重新生成 | 保留给定坐标和原子顺序。二维输入仍生成三维；单分子搜索保留输入构象并继续原有采样，给定复合物不先拆散重组 | `test_structure_builder`、`test_conformer_search`、`test_preorganization` |
| 廉价力场失败阻断后续 CREST/xTB | 坐标可用时把力场不支持或未收敛作为警告，后续方法可以接手；不把种子冒充已收敛极小值 | 同上及 xTB 路径测试 |
| 缺原生日志仍可报科学计算 done | 科学计算必须具备原生正常终止证据；普通 shell 保留退出码语义 | 远端计算及 Slurm 测试 |
| 子任务被别人的计算阻止结束 | 普通子任务只等待自己负责范围内的工作；Coordinator 仍查看全项目 | `test_runtime_v2_design_repairs`、schedule 测试；含真实场景 Harness 回归 |
| transcript 先截全部事件再筛消息 | 通过现有事件迭代器先筛消息，保持原 JSON 形状，分批输出完整历史 | `test_api_v2_history_threads`：600 条消息后追加 600 条工具事件 |
| 文件编辑要求模型维护哈希 | 删除公开哈希字段；程序使用同会话成功读写得到的已有版本。连续写、编辑无需机械重读，外部修改仍触发真实冲突 | workspace、工具语义、持久化及新设计回归 |
| 知识库故障伪装成成功零命中 | 返回本次来源错误及部分可用状态，保留其他正常来源命中；缺失数据不伪装为空库 | `test_runtime_v2_knowledge`、`test_knowledge_plugin`、`test_knowledge_store` |
| 修改项目目录时写到当前选中的另一个项目 | 点击对象贯穿操作，实际修改被点项目 | `App.actions.test.ts` |
| 输入框回答串到另一会话的问题 | 显示与发送共同按当前会话选择待答问题 | `composerSend.test.ts` |
| 后端拒绝业务操作仍提示成功 | 共同请求层检查已有 accepted 结果；创建成功不被后续刷新失败掩盖，异步事件与创建返回按 id 合并，避免重复项目 | `api.test.ts`、`App.actions.test.ts` |
| 大日志被按文件大小判为无证据并扣分 | 原生日志走已有真实解析链，完整读取频率、几何、终止和能量；文件大小不决定科学资格。附带元数据的限制不用于否定原生证据 | `test_benchmark_large_logs`：同一真实日志加空白越过 20 MiB 后，证据与评分保持一致 |

同根问题一并清理：普通空标题 MOL 输入不再被去除开头空行破坏；图结构读取不再强求力场收敛；过时启动器探测分支、公开哈希提示及无用科学扫描大小参数已删除。没有增加新的公开配置开关、工具必填字段或独立状态账本。

## IRC 修复与验收边界

虚频位移启发式异常保留 warning，继续检查真实方向证据；它不再提前挡住端点结果。原生 ORCA 输入坐标回显可用于静态频率几何及优化来源核对，不把优化或 IRC 的输入坐标冒充末帧。对应 `test_ts_guess`、`test_orca_frames` 及 TS/IRC/DAG/Benchmark 关联回归已通过。

IA8 原始请求和原始日志在当前源码上本地重验为 pass，可疑模式 warning 保留。该结果只代表本地源码验证，未替换旧服务回执，也未据此自动回填 Gold。

大日志修复沿用现有科学解析器，没有添加摘要证据、截断证据或新的通过标准。**原生解析器仍会完整读入文本，内存占用随日志增长；本轮没有解决通用大日志解析的内存优化。** 不再用科学负分隐藏这一工程限制。

## 验证结果与限制

已执行语法检查、Ruff、差异空白检查及前端生产构建，均通过。前端构建仍提示现有大 chunk 警告。没有运行本地测试全集。以下为各模块最后验证批次，存在重复用例，不相加成总数：

| 范围 | 结果 |
| --- | --- |
| 运行时、版本绑定、工具权限、持久化及事件循环保护 | 244 项通过；最后工具描述同步后另有 63 项目录/schema 回归通过 |
| 远端计算与 Slurm | 110 项通过、1 项环境跳过 |
| 结构、构象、预组织及路径 | 119 项通过，6 项真实 CREST 集成用例未执行；最后 MOL 空标题修复另有 5 项通过 |
| 启动器与 store 所有权 | 27 项通过 |
| 前端测试 | 15 个测试模块通过，类型检查及生产构建通过 |
| Benchmark、TS/IRC、DAG、记忆、知识库、历史 API | 下列 20 个相关测试文件批次退出码 0，4 项可选依赖跳过 |

```sh
UV_CACHE_DIR=/tmp/cloudra-uv-cache uv run --offline pytest -q \
  tests/test_benchmark_large_logs.py tests/test_benchmark.py \
  tests/test_benchmark_evidence_identity.py tests/test_benchmark_impossible.py \
  tests/test_dag_file_science.py tests/test_irc_endpoint_optimization.py \
  tests/test_irc_evidence_semantics.py tests/test_irc_atom_binding.py \
  tests/test_irc_separated_products.py tests/test_irc_lineage_wrappers.py \
  tests/test_ts_process.py tests/test_ts_guess.py tests/test_orca_frames.py \
  tests/test_memory_concurrency.py tests/test_memory_scope_guard.py \
  tests/test_runtime_v2_knowledge.py tests/test_knowledge_plugin.py \
  tests/test_knowledge_store.py tests/test_api_v2_history_threads.py \
  tests/test_no_sync_on_loop.py
```

额外执行的完整 Benchmark 脚本场景有三个未通过，相关批次随后中断，不能声称整链或全套通过，也没有用 HEAD 基线执行证明它们是既有失败：

- `test_cli_malformed_inputs_fail_then_corrected`：两次新建文本文件的实际断言通过，但后续模型脚本耗尽，`calc/input.gjf` 没有生成。
- `test_cli_guided_supervisor_loop[before_suspend]` 和 `[after_suspend]`：脚本未提交现有交付要求的 `mechanism_graph.json`，被原有交付检查拒绝，随后无进展退出。

该 FP 文件只删除两次新建 write 调用的公开哈希参数。没有为通过这些场景降低科学或交付要求。相关运行时、恢复和版本绑定测试在后续聚焦批次中通过；上述三个完整 FP 场景未重新宣称通过。

## 科学判据与评分规则：单独列明

1. **用户已授权并完成**：同一 TS 的真实双向 IRC 末帧分别优化到身份正确、零虚频的反应物和产物时，接受方向证明；几何区间及虚频位移启发式只提示可疑，不具有否决权。仍检查同源、真实起止几何、频率与身份，不用插值替代计算证据。
2. **用户已授权并完成**：不因日志超过扫描预算而将真实证据视为缺失。评分公式、阈值和造假惩罚未调整。
3. **未改、待人工裁定**：空图无日志但 Gold 非空时，空集合自洽为真产生的 0.3 总分。没有自行选择新的扣分方式。
4. **另一个工作流已有用户明确确认，本次随全部工作区推送**：IB9 E1 参考能垒从历史 14.74 更新为 GFN2-xTB 接触体参照的 5.65 kcal/mol。用户原话“我确定就是这个反应，回填吧”已核对。保留接触体真实软虚频，工具仍为 `inconclusive / missing TS geometry`，没有改为严格科学验收通过。E2 仍为空，评分权重未改。详见[IB9 回填依据与限制](../../gold_compute/queue_20261018/results/IB9/GOLD_BACKFILL_20261018.md)。

启动器修复不代表把现有服务热切到新源码；现有运行中的计算执行脚本也没有被改写。没有基于本轮单测声称线上已生效或两条题目均完成科学验收。
