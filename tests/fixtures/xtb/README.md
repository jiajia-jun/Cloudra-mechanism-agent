# xtb 输出测试样本

xtb stdout 日志（calculator.sh 重定向落盘的 `.out`），供 `cloudra/tools/core/xtb_frames.py`、`runtime/monitor.py` 的 xtb 终态判定与 `log_parser` 的测试使用。全部为合成小片段，格式参照 NA1_run 工作区真实 xtb 6.7.1 输出（GH #26）。

| 文件 | 任务类型 | 来源 | 许可 |
| --- | --- | --- | --- |
| `water_sp_xtb.out` | 单点（H2O，含 SUMMARY 块 / TOTAL ENERGY 表 / HOMO-LUMO GAP / 分子偶极 `full:` 行，`normal termination of xtb` 结尾） | 按真实 xtb 6.7.1 SP 输出结构合成 | — |
| `water_opt_xtb.out` | 几何优化收敛（`GEOMETRY OPTIMIZATION CONVERGED`） | 按真实 xtb 6.7.1 opt 输出结构合成 | — |
| `water_opt_unconverged_xtb.out` | 几何优化未收敛（`FAILED TO CONVERGE GEOMETRY OPTIMIZATION`，正常终止但应判 failed，GH #21 同款语义） | 按真实 xtb 6.7.1 opt 输出结构合成 | — |
| `ts_hess_xtb.out` | 频率（hess，含 `projected vibrational frequencies` eigval 块，1 虚频） | 按真实 xtb 6.7.1 hess 输出结构合成 | — |
