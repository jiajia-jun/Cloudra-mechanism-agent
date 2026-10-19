# 独立 IRC 作业端点交接与恢复

E1 的端点优化从 Gaussian corrector 前的 Input 坐标启动，验收以 completed point 的 CURRENT 坐标为准。这条实际几何断链不能通过补 atom binding、归档元数据或放宽几何比较来修复。原始计算记录继续保留，端点优化需要从规范外帧重做。

## 已实现

- 本地、Slurm 和远端回收后的 Gaussian/ORCA 日志自动导出可直接续算的双端 XYZ。它们与严格验收使用同一 `irc_endpoint_geometries`，保持原子顺序；A/B 不命名反应物或产物。
- 路径绑定原生日志 SHA256，读取时核对完整派生内容。非 IRC、异常终止、单侧、损坏或缺失的材料不返回双端。ORCA 需要已有的哈希绑定归档，不由导出器猜邻居边文件。
- 独立作业完成通知和 `query_compute_job` 交付 `irc_end_a_path`、`irc_end_b_path`；XYZ 进入 Artifact 归档。只读查询不创建文件，原生读取离开异步事件循环。
- 脚本内运行 QM 的 shell 作业不猜测其计算内容。提交原生 IRC 日志到 DAG 时，同样从不可变快照导出规范双端，并将路径写入恢复操作。
- 对已有不一致结果，验收点名原生起点不匹配的 Opt 日志，并给出重做 Opt → Freq 的实际 XYZ 路径。派生文件被删除、编辑或替换成符号链接时，缓存撤下失效恢复路径；原生科学判定不依赖派生文件。
- 工具说明、系统提示和 DFT 工作流统一为：正式 TS 求解及完整验证使用 TS process，独立 TS/IRC submit 用于探索性试算或能力探针；受阻时检查并修订当前 run。

没有新增 Agent 必填字段、frame/table selector、内部哈希要求或科学阈值。正常提交、正常终止与科学通过仍分别判断。

## E1 核验

原件来自 `evidence/e1-irc-20261019`，提交 `4f26105257d292deca0de0c3a8b434d2b8842b0d`。外部原件不随本修复合入。

现有真实 DAG 重放程序仍可复现原 E1 的 `frequency=passed`、`ts_opt=passed`、`short_irc=incomplete`；现在明确点名 rev5/fwd5 的错误起点并给出两个规范文件。原件和复制后的原计算文件哈希保持不变。

direct 恢复探针还通过公开 `qm_input_writer.tool_call` 生成了两份待重算 GJF。生成前严格核对原 E1 route、Opt 参数、泛函、基组、色散、积分设置、电荷、自旋和资源声明；生成后读回原生输入，确认设置保留且坐标符合严格端点同一性。没有生成虚构 Opt 日志或提交计算。

## 工程验证

相关模块分组覆盖共 451 项，均已通过；未运行本地全套。包括核心/执行归档 102 项、通知/查询/事件循环守卫 91 项、科学链与 DAG 交付 44 项，以及缓存、入口引导、工具契约和提示预算等 214 项。最后一组首轮出现两条旧 format 6 夹具失败：旧状态被现有程序隔离，测试尚未进入其原本要核对的提示保留行为。夹具改用 format 7 与显式工程 checkpoint，原断言保留，最终 guidance 全模块 96 项通过。生产执行逻辑没有为旧格式增加兼容分支。

全仓 `compileall`、`ruff check cloudra tests` 和 `git diff --check` 通过。通知/契约测试仍有第三方 nmrglue/NumPy dtype 弃用告警。独立审查后的三项缓存损坏回归明确保证：只撤下损坏的恢复路径，不影响原生有效链的科学通过。

复现入口及实际结果见 [证据目录](../evidence/irc_handoff_20261019/README.md)。完整的新调用链真实源码见 [源码快照](../evidence/irc_handoff_20261019/source-chain.md)，原生解析器、提交和调度的未改调用链见 [先前审计附录](../evidence/qm_consistency_20261019/source-chain.md)。

以上验证不代表完成了新的 Gaussian/ORCA 计算或整题 easy 重跑。E1 旧 Opt/Freq 仍需从导出坐标重算，完成科学验收后再绑定交付。此前审计 A1–A7 中的其它待修问题，包括 A6 的上游边文件归属问题，不因本次交接修复而消失。
