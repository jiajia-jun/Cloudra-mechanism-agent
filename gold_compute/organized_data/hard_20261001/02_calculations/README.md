# 计算证据：题目 → 作业 → 文件

`jobs.csv` / `jobs.json` 包含最终 compute.db 的 90 个作业。每个 job 目录有原账本记录，并链接真实输入、原始日志及完整运行目录；Hessian、GBW、轨迹、临时文件、报告与拒收尝试均在原目录保留。

目录名不代替化学身份：HI1 的 working major/minor 面标签交换已在结果说明纠正。`HA8` 是原 `H6PI`，`HB10` 是原 `HDA_CN`。

所有活跃账本状态为零。尚未找到的预期路径在 `path_gaps.json` 明示，不能默默假装已找到；可从 catalog.sqlite3 的 files 表及历史快照继续追溯。未被本轮账本登记的 standalone xTB/初猜资料仍在 raw_case 与总文件索引中。

状态 DONE/failed/cancelled 是程序/调度状态；科学接受、拒收、重复鞍点、错误物种与诊断扫描需看独立结论。旧 HE3/HG2 的退出证据也保留。

本轮预期 QM 输出缺少 job38 和 job50：38 在 guard 权限检查失败、未开始 QM；50 为用户取消的 READY 作业、未开始 QM。其账本、guard/取消证据和输入仍保留，并非两个已完成日志丢失。

`case_inventory.csv` 按题目/快照/文件类别汇总。unassigned 表示文件路径不能确定题目归属，仍保留在全部快照与总文件索引中，不按模糊名字强行归类。
