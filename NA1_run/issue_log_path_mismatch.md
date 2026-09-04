## Bug: compute job 报告的 `log_path` 与 guard 实际日志路径不一致（ORCA / macOS 不写 `.out`/`.log`）

### Summary
`query_compute_job` 与计算完成通知给出的 `log_path` 指向**根本不存在的文件**，而 guard 真正写入的日志在 `.cloudra/calc-<id>.out.log`。一个依赖 job 记录的 `log_path` 去 `log_parser` 的 agent 会直接失败；且不同入口报的路径还不一致（通知报 `.out`，query 报 `.log`）。

### Repro（本机 2026-09-04，ORCA 6.1.1 macOS arm64）
提交 `qm_input_writer(engine='orca', external_program='.../mace')` 生成的 `acetaldehyde_opt.inp`：
- `query_compute_job(job_id=25)` 返回 `log_path: .../NA1_run/acetaldehyde_opt.log`
- 完成通知（compute notify broker）显示 `Log file: .../NA1_run/acetaldehyde_opt.out`
- 实际：两者都不存在。文件 `ls NA1_run/` 无 `acetaldehyde_opt.out` / `.log`；真实日志在 `NA1_run/.cloudra/calc-25.out.log`。
- guard 的 per-job 状态文件 `state_25.json` 里正确记录 `"log_file": ".../.cloudra/calc-25.out.log"`。

### 根因
`cloudra/infra/compute_utils.py::get_log_path(input_file, job_type)`：
```python
if job_type == "gaussian":
    return str(path.with_suffix(".log"))
return str(path.with_suffix(".out"))   # ORCA/CP2K/VASP
```
假设 ORCA 生成与输入同名 `.out`。但本机 ORCA(macOS arm64 构建) **从不写 `.out`/`.log`**，主输出全写 stdout；guard 已改为把 stdout/stderr 捕获到 `.cloudra/calc-<id>.out.log`。于是预测路径永远是错的。

### 影响
- agent 依据 `query_compute_job` 返回的 `log_path` 去 `log_parser` 解析 → 找不到文件。
- 两个入口（query vs notify）给出的路径还不一致，进一步迷惑。
- 正确路径只在 guard 的 `state_<id>.json` 里，agent 需绕过 job 记录去读它。

### 建议修复
- `get_log_path` 对 ORCA 应返回 guard 实际产物路径：当 `.cloudra/calc-<id>.out.log` 存在时优先用它；或至少让 query/notify 从 `state_<id>.json` 的 `log_file` 字段读取真实路径。
- 统一 query_compute_job 与完成通知的 log_path 来源（应一致）。

### 环境
- cloudra 当前工作树（2026-09-04），`compute_utils.py::get_log_path`、scheduler/compute notify broker。
- 复现：`NA1_run/acetaldehyde_opt.inp`（job 25）、`NA1_run/probe_b3lyp.inp`（job 26）。
