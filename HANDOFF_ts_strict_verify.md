# HANDOFF — ts_guess strict verify 两处增强（改动 1 + 改动 2）

Status: COMPLETE. 无 git commit/push（等用户指令）。

## 跟进（改动 3，纯文本可操作提示）— 已完成
- 只在 ts_guess 追加文本，不改任何判据/阈值/verdict 取值。
- 新增常量 `_IRC_TRUNCATION_REMEDY`（cloudra/tools/Chemtool/ts_guess.py）：提示 IRC 可能截断、
  外侧帧尚未松弛到中间体 → 对 IRC 外侧帧补做端点优化（Opt，建议带 Freq 确认 0 虚频），
  把优化后的极小结构作为 reactant_path/product_path 重新提交。
- `_strict_path_verdict` 内新增局部 `_non_pass(reason)`：把提示 append 进 checks 并拼进 verdict。
  覆盖的非 pass 分支：缺端点优化中间体 / 拿不到双向端点 / 缺 TS 几何 / 几何区间不可判 /
  几何区间证明失败(fail)。通道 2（收敛证据）失败时若整体 non-pass 也经以上分支带出提示。
  已确认 pass 场景 checks/verdict 均不含该提示。
- 新增单测 `test_verify_strict_non_pass_appends_endpoint_optimization_remedy`（覆盖缺中间体 + 区间失败两分支）。
- 实测：`uv run ruff check cloudra` → All checks passed；
  `uv run pytest tests/test_ts_guess.py tests/test_tool_semantics.py tests/test_benchmark.py` →
  **223 passed, 4 skipped, EXIT=0**（较上次 +1 新测）。

## 改动文件（仅这三个是我改的；仓库里 benchmark/ideapool 等改动是既有脏文件，非本次）
- cloudra/tools/core/orca_frames.py  (+116/-3)
  - 新增 `vibdisps_from_text(text, n_freqs, n_atoms)`：解析 ORCA NORMAL MODES 位移块，
    返回 (n_modes, n_atoms, 3)。版式=模式号表头 + 3N 行笛卡尔分量（行首为分量号 c，
    (atom,dir)=(c//3,c%3)，列=该子块内各模式）。只取最后一个 VIBRATIONAL FREQUENCIES
    之后的块；频率数须 == 3*n_atoms。
  - `_orca_sidecar_roots`：stem 回退额外加入日志目录的父目录。
  - 新增 `_sidecar_search_dirs` / `_basename_matches_any_job`；`_irc_endpoint_sidecar` 增加
    兜底：在日志目录/父目录 glob `*_<suffix>.xyz`(=final) 与 `*_<suffix>_trj.xyz`(=traj)，
    唯一命中才接受；多命中按候选作业名前缀去歧义，仍不唯一则拒绝。新 origin:
    final_endpoint_file_glob / trajectory_last_frame_glob。
  - `read_endpoint_geometry`：origin 判定由 `!= "trajectory_last_frame"` 改为 `"trajectory" not in origin`，
    以兼容新增的 *_glob origin。
- cloudra/tools/Chemtool/ts_guess.py  (+129/-15)
  - `_parse_freq_log`：engine=="orca" 时 vibdisps 走 orca_frames.vibdisps_from_text；
    positions/symbols 走 orca_frames.final_xyz_from_text + irc_path.parse_xyz（cclib 对 ORCA 6.1
    整体崩溃，原代码 positions 恒 None → strict 几何区间层会 inconclusive）。
  - 新增常量 `_ENDPOINT_INTERMEDIATE_SAME_SPECIES_RMSD_ANG = 0.6`。
  - `_strict_path_verdict`：新增通道 2 调用 `_endpoints_converged_to_intermediates`；
    原「几何区间证明」作为通道 1 原样保留（仅重排进 if 块）。
  - 新增 `_endpoints_converged_to_intermediates(aligned_positions)`：逐对距离矩阵 rmsd，
    direct/swapped 取更小者，两侧都 ≤0.6 Å 才 pass；两中间体须可区分(rmsd>阈值)否则跳过。
- tests/test_ts_guess.py (+185) 新增 5 个测试（见下）。

## 实测（fixture: gold_compute/campaign/runs/F1/F1_E1/16/ts06 + /18）
- ts_guess(mode=verify, strict=True, engine=orca, freq=16/ts06/calc-410.out.log,
  irc=16/ts06/calc-411.out.log, reactant=18/IRC_F/ep_optfreq.xyz, product=18/IRC_B/ep_optfreq.xyz,
  watch_pairs=[[1,2],[2,6]], charge=-1) → verdict 以 "pass:" 开头；imag_mode_aligned=True。
- 新增测试 5 个：orca_vibdisps_from_text_parses_normal_modes_block /
  parse_freq_log_orca_text_vibdisps_and_orientation /
  orca_irc_endpoints_glob_finds_sidecars_for_renamed_log /
  orca_irc_endpoints_glob_refuses_ambiguous_match /
  endpoints_converged_to_intermediates_channel  —— 全绿。
- `uv run pytest tests/test_ts_guess.py tests/test_tool_semantics.py tests/test_benchmark.py` →
  **222 passed, 4 skipped**, EXIT=0。加 tests/test_orca_frames.py 一起 → 253 passed, 4 skipped, EXIT=0。
- `uv run ruff check cloudra` → All checks passed。

## 共享口径影响判断
- 改动 2 只落在 ts_guess，**未**改 irc_path / benchmark selfconsistency → benchmark 评分口径不变。
  若要同步，需要 Coordinator 决策（且需定 _ENDPOINT_INTERMEDIATE_SAME_SPECIES_RMSD_ANG 的值）。
- 改动 1b 落在共享模块 orca_frames：benchmark selfconsistency 的 _orca_irc_endpoint_geometries 同源
  → 在「边文件在、但 NAME/stem 推不出作业名」时 benchmark 现在也能找到端点。属同口径的鲁棒性增强，
  不放松任何几何判据。改动 1a（vibdisps）与 ts_guess 内新增的 ORCA TS 几何仅 ts_guess 使用，benchmark 不受影响。

## 待 Coordinator 确认
- 改动 2 的收敛阈值 _ENDPOINT_INTERMEDIATE_SAME_SPECIES_RMSD_ANG=0.6 Å（我选的保守值；
  fixture 上 A=0.229 / B=0.492，错配 0.855~1.18 被排除）。这是新增判据阈值，请确认或改值。