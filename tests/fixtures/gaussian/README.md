# Gaussian 日志测试样本

真实 Gaussian 输出日志，供 `cloudra/tools/core/gaussian_frames.py` 的测试使用。

| 文件 | 任务类型 | 来源 | 许可 |
| --- | --- | --- | --- |
| `hcn_ts_irc_g16.log` | IRC（G16，含 `Summary of reaction path following` 汇总表，正/反向各 10 点 + TS，两端均 maxsteps 未收敛） | <https://github.com/mizu-bai/Gaussian-MOKIT-Molpro> `example/HCN/gau/HCN-ts-irc.log` | BSD-2-Clause |
| `h2_scan_g09.log` | 松弛势能面扫描（G09，`opt=(ModRedundant)`，100 步 H-H 键长扫描） | cclib-data `Gaussian/Gaussian09/relaxed_PES_testH2.log`（<https://github.com/cclib/cclib-data>） | BSD-3-Clause |
| `water_opt_freq_g16.out` | opt+freq（G16，水分子，5 个优化步，3 个频率） | cclib-data `Gaussian/Gaussian16/water_neutral_nbo_opt_freq.out` | BSD-3-Clause |

选取标准：文件尽量小、单步任务（无 Link1 多步）、格式为 Gaussian 官方输出原样。
