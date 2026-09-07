# ORCA 日志测试样本

真实 ORCA 输出日志，供 `cloudra/tools/core/orca_frames.py` 与 `log_parser` 的测试使用。

| 文件 | 任务类型 | 来源 | 许可 |
| --- | --- | --- | --- |
| `co2_freq_orca42.out` | opt+freq（ORCA 4.2，CO2，含 THERMOCHEMISTRY 块，4 个频率含 0 虚频） | cclib-data `ORCA/ORCA4.0/CO2_freqs.out`（<https://github.com/cclib/cclib-data>） | BSD-3-Clause |
| `dvb_opt_orca42.out` | 几何优化（ORCA 4.2，divinylbenzene，4 个优化步，收敛） | cclib-data `ORCA/ORCA4.0/dvb_gopt.out` | BSD-3-Clause |
| `dvb_scan_unrelaxed_orca42.out` | 非松弛面扫描（ORCA 4.2，D7 二面角 0°→360° 共 12 点） | cclib-data `ORCA/ORCA4.2/dvb_scan_unrelaxed.out` | BSD-3-Clause |
| `cope_irc_extopt_mace_orca611.out` | 外部 MLIP IRC（ORCA 6.1.1 `! ExtOpt IRC` + MACE-OMol25，能量行只有 `(From external program)` 变体，正常终止） | 按 P1 Cope job22 实测日志结构缩写合成（原始日志随工作区清理删除） | — |
| `cope_relaxed_scan/` | 松弛扫描逐帧结构 + `relaxscanact.dat`（供 `ts_guess scan_parse` 测试） | P1 Cope 任务实测产物 | — |
| `extopt_relaxed_scan/scan_extopt_snippet.out` | 外部 MLIP 松弛扫描文本片段（`! ExtOpt`，能量行带 `(From external program)` 后缀，5 帧 × 2 坐标块，内部峰在帧 3） | 按 MACE-OMol25 relaxed scan 实测日志结构缩写合成（GH #23，原日志已随工作区清理删除） | — |
| `extopt_relaxed_scan/scan_extopt_grouped.out` | 同上内容 + 每个扫描点前的 `RELAXED SURFACE SCAN STEP N` 标记（ts_guess 文本回退按扫描步分组解析所需；帧能量取每步收敛后的最后一条） | 由 `scan_extopt_snippet.out` 加回实测日志中的扫描步标记合成（ts_guess G1 修复配套） | — |
