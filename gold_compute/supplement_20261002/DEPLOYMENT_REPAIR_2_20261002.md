# Cloudra 第二次修复部署（2026-10-02 04:35 SGT）

用户授权“修了新bug，部署一下。有任何流水线bug通知我”。部署 `1e694a8fddab58ea822d9edb0e91bd556766b34e`，主分支等价修复 `4932932dab`；采用修复分支发布保留已上线 MCP 内容，只变更八文件。新目录 `/opt/cloudra/releases/20261002-1e694a8f`，旧 fc854066 独立发布完整保留。

## 修复与独立验收

审批严格接受布尔值，不将字符串 false 误判为批准，移除正则兜底；原有审批设置保持。ORCA 渲染保留辅助基组 def2/J，正确处理基组首尾空白、带空白的方法分隔符。

本轮 compileall、ruff 通过，186 项聚焦测试通过（零失败，原日志 `/private/tmp/cloudra-deploy-1e694a8f-tests.log`）；修复会话主分支聚焦验收另有 287 项通过、4 项缺原始日志跳过。全发布 4,367 文件 / 706,642,634 字节 SHA 逐项一致。线上实际导入函数已验证严格审批与正确方法渲染。

两 API active，唯一调度器 PID 194525 cwd 新版，journal 无新错误。首次即时快照在自动调度器启动前，稍后已独立复核唯一进程；首次快照保留，未手动重复启动。原 12 会话 ID 保留；部署前 28,845 事件前缀逐行一致，6 provider pause pin 保留；四现用 SQLite integrity ok，8 配置/凭据/启动文件 SHA 不变。99 QM 持锁运行，输入 SHA 未变，日志 7334766 → 7901147，无新增作业。仅 API 与独立调度器优雅切换，未操作 QM。

## 暂停与通知

DeepSeek 未确认恢复，新增补算暂停；99 系统检查点仍 provider_outage_pause / waiting_for job:99。六 context pin 保留，不自动解除、换模型、唤醒失败会话或重交。手工 TS/IRC 禁令保留。SHARK 根因及真实 TS/IRC 全链仍未验。

原 ny3-gold 五分钟跟进已更新：任何新出现的流水线 bug 均及时通知用户；已知同一问题无变化不重复，健康静默。

## 私有备份

部署前 `/private/tmp/cloudra-predeploy-1e694a8f-20261002`：15 文件 / 121,027,756 字节 SHA 全一致，四 SQLite backup 一致快照 integrity ok；远端 runtime/monitor_incidents/predeploy_1e694a8f_20261002。切换及验收 `/private/tmp/cloudra-deploy-1e694a8f-20261002/DEPLOYMENT_VERIFICATION.json`；前后监测 `/private/tmp/cloudra-monitor-predeploy-1e694a8f.json`、`/private/tmp/cloudra-monitor-postdeploy-1e694a8f.json`。私有目录700/文件600，不入Git。正式收尾纳入独立补算完整归档，原冻结archive/organized_data不覆盖，仍需平台停费。
