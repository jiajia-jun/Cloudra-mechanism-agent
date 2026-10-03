# 实验版 Cloudra 修复部署（2026-10-02 04:09 SGT）

用户明确授权“新版部署”后，部署 `fc8540669870d94eca417531bd2d5e3cf331464d`（修复分支 codex/ts-irc-rendering-fix）。发布目录 `/opt/cloudra/releases/20261002-fc854066`，原 `/opt/cloudra/releases/20261002-52477b99` 保留。

## 验收

- 发布包和 4,367 个文件逐项 SHA 一致（706,638,067 字节）；语法检查通过。
- 本轮独立聚焦测试 107 项通过，覆盖渲染、持久恢复、扫描故障、手工 TS/IRC 禁令及 MCP surface；修复会话另有完整离线回归报告。
- 两个 API 服务 active；唯一调度器 PID 187821，实际 cwd 为新版目录。
- 原项目 12 个会话 ID 全保留；部署前 28,826 条事件逐项摘要比对一致，部署后 28,845 条；6 条 provider 暂停 pin 均保留。
- 四生产 SQLite integrity_check 全部 ok；配置、nodes、凭据环境与启动脚本 SHA 全不变。
- 99 号计算仍持有计算锁，绑定输入 SHA 不变，日志从 6,026,138 增至 6,131,484 字节；没有新补算入队。只优雅重启 API 和独立调度器，未触碰 QM 进程。

## 暂停与科学边界

DeepSeek 中断尚未确认恢复，全部新增补算继续暂停。发现自动流水线不读取 Agent 的自然语言 pin，已通过既有检查点接口给 99 流水线增加可恢复的 `provider_outage_pause`，保留 `waiting_for=job:99`、现有作业及输入。恢复前必须核对 provider，并由监工明确解除暂停；不能直接复跑失败任务。

补丁修正统一 ORCA 基组拼写，并保留方法关键词、重复调整时的故障和预算、扫描原生日志诊断。SHARK 根因仍未定位；没有真实 TS/IRC 整链验收成功，手工 TS/IRC 提交禁令保留。

## 私有备份与证据

部署前专用备份：`/private/tmp/cloudra-predeploy-fc854066-20261002`，15 文件 / 120,956,116 字节，逐项 SHA 一致、四 SQLite backup API 一致快照 integrity ok。私有文件 600 / 目录 700，不提交 Git。

版本切换证据：`/private/tmp/cloudra-deploy-fc854066-20261002/DEPLOYMENT_VERIFICATION.json`。流水线暂停前后检查点：`/private/tmp/cloudra-provider-pipeline-pause-20261002`。部署前后全量监测位于 `/private/tmp/cloudra-monitor-predeploy-fc854066.json` 与 `/private/tmp/cloudra-monitor-postdeploy-fc854066.json`。

先前 03:56 provider 快照清单误包含关闭连接后消失的 WAL/SHM，未通过完整 SHA 核验；已明确标记未验收，由本次独立完整部署前备份补齐证据。旧目录与冻结 final_archive / organized_data 均保留。最终收尾须把所有私有 incident、上下文与数据库一致快照归入补算独立完整归档，再核对正确实例平台停计算计费。
