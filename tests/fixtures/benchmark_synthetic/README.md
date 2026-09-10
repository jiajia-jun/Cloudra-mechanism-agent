# 合成契约 fixture（benchmark 交付物评分测试用）

**这些不是科学计算结果**，只是传输/契约测试材料：由真实 ORCA 日志 fixture
（`tests/fixtures/orca/co2_freq_orca42.out`）派生，仅做两处合成改动：

| 文件 | 改动 | 用途 |
| --- | --- | --- |
| `minimum_freq.out` | 原样 + 首行加 `smiles: O` 协议注释 | 充当"起点最小值"日志（0 虚频） |
| `ts_freq.out` | 首个振动频率取负（标记一阶鞍点）+ 末次 `FINAL SINGLE POINT ENERGY` 平移 +0.0318 Ha ≈ 19.955 kcal/mol | 充当"过渡态"日志（恰 1 虚频） |

因此 `E(TS) − E(min)` ≈ 19.955 kcal/mol，供
`tests/test_benchmark.py::test_barrier_is_derived_from_logs_and_must_be_declared`
等用例断言"交付 JSON 声明值必须与日志推算值一致"的评分契约。

真实引擎能力验证另见 `test_real_xtb_engine_run` 与
`test_real_orca_progext_external_interface`（真机跑，不用这些合成件）。
