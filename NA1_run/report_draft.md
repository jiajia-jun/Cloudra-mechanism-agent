# NA1 乙醛自醇醛加成 -> 3-羟基丁醛 — 计算与 harness 问题报告（草稿）

工作目录(沙盒根): /Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_run
方法白名单: ['mace-omol25','xtb']; 目标引擎 = ORCA `! ExtOpt` + `%method ProgExt`(MACE-OMol25) / 或 xTB。
机制(题单 gold): R(OH-+2CH3CHO, charge -1, mult 1) -> TS1(烯醇负离子生成,H2O) -> I1(烯醇+水+乙醛 central_complex)
-> TS2(RDS C-C 加成 Burgi-Dunitz) -> I2(beta-羟基烷氧负离子+水) -> TS3(水再质子化, 回收 OH-) -> P(3-羟基丁醛+OH-)。

## 关键结果(pending job 28/29)
- mechanism_graph.json: 已写, 合法 JSON (7 nodes / 3 edges), 覆盖 gold 机制子图。
- RDS 弛豫扫描: 见下 "scan 病态行为", 未能给出可靠能垒。
- TS2 OptTS (job 29): 运行中。

## 方法白名单【未生效】(最关键 harness 问题 #1, 3 层全部确认)
本 live 会话未注入 MethodPolicyStage (cloudra/benchmark/policy_stage.py 由 backend.py 追加, 但子代理管线未挂上)。
- qm_input_writer(method='b3lyp') -> is_success true, 生成 probe_b3lyp.inp (`! Opt b3lyp def2-svp`)。
- submit_compute_job(probe_b3lyp.inp) job 26 -> 实际跑通 B3LYP, state=done, 最终 E=-153.62828 Ha。
  (对照: coordinator 说明 benchmark 下会被拦截; 本会话不拦截。job 26 为对照探针, 非机制证据。)
- bash heredoc 写 probe_bash_b3lyp.gjf (`# opt b3lyp/6-31g(d)`) 未拦截; 仅触发另一个 "bash habit" guard 警告。
  (说明: bash_habit_guard 与 MethodPolicyStage 是两个独立 guard; 前者警告, 后者未拦。)

结论: 方法白名单在本运行时完全未拦截。这既是 harness 失效, 也是我应报告的第一发现。

## log_path 不一致 (#2, 确认)
同一任务出现三条互斥 log 路径, 真实日志只能靠 state_<id>.json 或 `.cloudra/calc-<id>.out.log` 定位:
- 终态通知: "Log file: .../probe_b3lyp.out" (不存在)。
- query_compute_job: log_path=<stem>.log (query_compute_job.py:_row_to_dict 对 .gjf/.com/.inp 一律 base+".log";
  对 ORCA(.inp) 错; 且 macOS ORCA 从不写 .out, 实际是 `.cloudra/calc-N.out.log`)。
- state_26.json log_file: `.cloudra/calc-26.out.log` (正确)。
根因: monitor.py 有 `_resolve_log_target` 回退到 calculator stdout 落盘; 但 query_compute_job 用硬编码 .log, 通知用 .out。

## conformer_search 病态 (#3, 确认)
输入 combined SMILES [O].C=C[O-].CC=O (charge -1), backend rdkit (crest 未装, 只有 rdkit)。
- "Force field: UFF", 120 confs rel E 全部 = 0.000 (能量退化, UFF 未给出有效能量)。
- distance_filters atoms[2,6] 2.2-2.8A -> passing_filters=0 (0 个反应构象)。
- 无法用它构建离子-偶极络合物起点 => 只能手工拼几何。

## 几何优化"done 但未收敛" (#4 = coordinator GH#21, 我独立复现)
I1 络合物 MACE Opt (job 27): state_27.json optdone=false, geovalues 51 轮未达收敛, 但 is_success=true / state=done
(因日志含 `ORCA TERMINATED NORMALLY`)。实际几何未收敛; 且络合物分离 (烯醇-乙醛 C-C ~4.2 A)。
cclib 能给出 optdone=False, 但 guard/log_parser 未用它判定。=> 不要轻信 state=done = 几何收敛。

## log_parser 对 MLIP 外部能量的处理 (#5, 修正后 = coordinator 新增 GH#22)
勿以偏概全: 对已收敛 MACE Opt (job 25), ORCA 会打印两次 `FINAL SINGLE POINT ENERGY (From external program)`
(line 349 初始, line 1430 收敛), final_energy_hartree 取最后 = 正确 (log_parser 返回 -153.82755, 正确)。
缺陷是**在未收敛 opt**上 (job 27): ORCA 只在到达收敛几何时才打印第二个 FINAL SINGLE POINT ENERGY;
maxiter 耗尽时只打印一次 (初始, -383.41894); 每轮能量是 `Current Energy` (被正则忽略) =>
final_energy_hartree 返回初始能量 (~0.126 Eh 高于最优几何)。这是 #4(#21) 的数值后果, 应作为独立数值提取缺陷。
(代码: cloudra/tools/core/orca_frames.py final_energy_hartree / _FINAL_ENERGY_RE。)

## qm_input_writer 输出缺陷 (#6)
- ORCA 输入不写 title/smiles 注释: 我在 4 个 .inp 手动加 `# smiles: <SMILES>` 以满足证据注释要求。
- qm_input_writer 对 ORCA 将 freq 任务映射为 `Freq` (解析 Hessian), 但外部 MLIP (ExtOpt) 无解析 Hessian,
  需 `NumFreq`。我手动把 ts2_optts.inp 从 `! ExtOpt OptTS Freq` 改成了 `! ExtOpt OptTS NumFreq`。

## ORCA 弛豫扫描病态 (#7 = 化学+harness)
ts2_scan.inp (`! OPT ExtOpt`, %geom Scan B 0 7=2.6,1.5,14 end, C(alpha)-C(carbonyl)): 每个扫描点都不收敛
("The optimization has not yet converged - more geometry cycles are needed" x140+), 已达 9/15 个点;
能量从 -383.5 (起点) 到 -383.088 (step 8, 相对高约 280 kcal/mol, 物理不可能) => 非收敛几何导致能量失真。
relaxscanact.dat / ts_scan.*.xyz 只在任务终止时才写(运行中为空)。=> 该 1D 弛豫扫描对松散离子-偶极
络合物 + 冻结单坐标 无法收敛, 不能给出可靠 RDS 能垒。印证 SOP 提醒 (1D 不足以抓 2 坐标耦合反应)。

## 历史终态误判 (观察, 疑似)
query_compute_queue 终态记录: job 22,23,24 (先期会话, ORCA MACE) state=failed, last_error 尾部为
"...****ORCA TERMINATED NORMALLY**** | TOTAL RUN TIME:..." => 正常终止却被打 failed。
疑为 GH#17/#18 类 MACE NumFreq/IRC 误判。state 文件已清理, 未能进一步取证 (标注 suspected)。

## 可运行/证据产物 (绝对路径)
- mechanism_graph.json (合法): /Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_run/mechanism_graph.json
- I1 络合物 MACE opt: I1_complex_mace_opt.inp (+ .cloudra/calc-27.out.log, 未收敛 done)
- RDS 扫描: ts2_scan.inp (+ .cloudra/calc-28.out.log, 病态)
- TS2 OptTS: ts2_optts.inp (+ .cloudra/calc-29.out.log, 运行中)
- 对照(白名单探针): probe_b3lyp.inp / probe_bash_b3lyp.gjf (非机制证据)
- 几何拼装: I1_complex_guess.xyz, ts2_guess.xyz (conformer_search 失败后手工拼装)

## TS2 OptTS (job 29) 结果: 未收敛, 无 n_imag==1
- log_parser: scf_energy=-383.1756 (初始几何能量), frequencies_cm=null, job_type=[freq,opt,ts]。
- 日志: "Hessian has 2 negative eigenvalues" (非 1 阶鞍点), "Searching for lambda that maximizes along the lowest mode",
  其末 "The optimization did not converge but reached the maximum number of optimization cycles" => 又未收敛 (GH#21 复现)。
- 无 VIBRATIONAL FREQUENCIES 块 (NumFreq 因未收敛未产出/未被提取)。
- 末态几何 ts2_optts.xyz E=-383.5048: 烯醇 alpha-C(atom1) 与醛基碳(atom8) C-C 增大到 ~3.6 A (TS 搜索往回走, 未找到 C-C 加成鞍点)。
=> 未获得有效 TS2 (n_imag==1 未达成), RDS 能垒无法可靠计算。

## RDS 能垒结论 (partial)
无法给出可靠 RDS ΔE‡: (a) I1 central_complex Opt 未收敛且络合物分离 (job 27); (b) RDS 1D 弛豫扫描病态
(job 28); (c) OptTS 未收敛且远离鞍点 (job 29)。已按真实情况记录为"未可靠计算 + 问题清单"。

