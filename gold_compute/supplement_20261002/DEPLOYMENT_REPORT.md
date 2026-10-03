# Cloudra 最新版部署与补算恢复

## 已完成

- 部署本地干净HEAD `52477b99f7cc81841318014feef15926a30db9c5`，远端 `/opt/cloudra/releases/20261002-52477b99`。
- `/opt/cloudra/source` 指向新版，旧源码原样保留 `/opt/cloudra/source_preupgrade_20261002`。
- API8420/8422和唯一调度器已加载新版；所有原项目调用继续使用8422。
- 1,044文件SHA一致；Python依赖匹配最新版pyproject。
- 语法/聚焦ruff通过，126项Python测试、18项JS宿主测试通过；前端按最新版锁文件Vite8.3.1构建，HTTP200。
- 部署前5SQLite已用backup API存一致快照，远端/本地integrity_check全部ok。原11会话、22,025事件、context保留；配置/nodes/token逐项SHA不变。
- 已确认部署窗口无活跃QM和READY，五执行者已先交接暂停再收到一次恢复；没有中断科学计算。

## 预算与本轮状态

用户允许用剩余57元补十条审计缺口。本次核对智算云实时余额51.93元无欠费（约01:41 SGT），超算控制台57并非原实例实时余额。原实例42.81.102.25于约01:33重新开机按量计费。不充值、不新机。

补算还未完成；恢复后待真实提交/终态科学验收。HL1准备报告自设MaxIter400与约束冲突，已明确要求删除未提交输入上限；HI1 RC51仅适用C-C加成，不能当E1缩合初始参考，已纠正。

## 保全与后续

私有配置与数据库位于本目录deployment_backup，权限700/600；不可提交Git/公开。新计算和交接快照位于remote_round_snapshot，原final_archive与organized_data不可覆盖。按预算监控必要唯一作业，通过全部证据才回填；若需要合并/拆边，先据真实PES给出科学裁决，不硬造能垒。终态完整增量及SQLite一致快照核验后平台停正确实例计算计费。
