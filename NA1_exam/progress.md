# NA1 模拟考试进度（乙醛自羟醛加成 → 3-羟基丁醛，[OH-] 催化，charge -1, singlet）

工作目录: /Users/cloudrayyy/Desktop/Cloudra-mechanism-agent-master/NA1_exam/
方法白名单: MACE-OMol25 (ORCA ExtOpt, ProgExt=/Users/cloudrayyy/miniconda3/envs/chemai/bin/mace,
  Ext_Params="--model /Users/cloudrayyy/opt/mace-omol25/MACE-omol-0-extra-large-1024.model --device cpu --dtype float64") + xTB。
真实日志位置: NA1_exam/<dir>/.cloudra/calc-<jobid>.out.log（通知里的路径常不存在）。
调度器常误判 ExtOpt 作业成败；以日志文本 'ORCA TERMINATED NORMALLY' + 'THE OPTIMIZATION HAS CONVERGED' 为准。
ExtOpt 组合 opt+freq 会静默跳过 freq —— 频率必须单独 NumFreq 作业。
scheduler 拒绝 job_type=xtb —— xTB 走 bash CLI (/Users/cloudrayyy/miniconda3/envs/chemai/bin/xtb)。

## 机理图（DAG 已接受，mechanism_graph.json 已写）
R [OH-].CC=O.CC=O →(e1) I1 C=C[O-].O.CC=O →(e2) I2 CC([O-])CC=O.O →(e3) P [OH-].CC(O)CC=O

## 物种能量（MACE-OMol25, Ha; G 为 298.15K）
- R : E=-383.5165907 G=-383.4336723 (job45, calc-45) ✓ supported
- I1: E=-383.5468773 G=-383.4605867 (job42, calc-42) ✓ supported
- I2: E=-383.5533544 G=-383.4615300 (job46, calc-46) ✓ supported
- P : job49/50 E=-383.5126982 G=-383.4222152 ✗✗ 身份错误！结构是 CH4 + HOCH2-O-CH=CH-O(-)
  （RDKit 感知+距离矩阵+渲染证实；job49 从正确的 P_initial.xyz 漂移）。P 三阶段绑定不可信，
  需重做（已告知 Supervisor）。正确初始结构: species_P/P_initial.xyz。

## 边状态（revision 26）
- e1 (R→I1, 质子转移): ts_guess ✓(IDPP idpp_e1/img_06); ts_opt ✓(calc-82, E=-383.519556, 比 R 低 ~1.9 kcal，鞍点身份待频率仲裁);
  frequency 欠——必须在 calc-82 几何上重做 NumFreq（calc-80 是在未收敛 calc-79 几何上做的，4 个虚频被拒）。
  若 0 虚频 → calc-82 是簇最小值，ts_opt 绑定会被重审。
- e2 (I1→I2, C-C 形成, RDS): ts_guess ✓; ts_opt ✓(calc-53, E=-383.5314058); frequency ✓(calc-78, 唯一虚频 157.93 cm-1, G=-383.43663)。
  欠 short_irc → endpoints → direction → identity → thermochemistry。job89/90 = 端点弛豫候选（converged minima）。
  job91 (e2_mace_scan) failed 未收敛，非必需。
  初步能垒: ΔE‡(I1→TS2)=+9.7, ΔG‡=+15.0 kcal/mol；相对 R 为负（I1 远低于 R）。
- e3 (I2→P, 质子回传): ts_guess ✓(IDPP, 但是对着错误的 P 锚点做的); ts_opt rejected。
  子代理诊断: xTB 扫描单调 +20.1 kcal 无峰; MACE SP 同帧单调 (+3.7→+15.2); 盆坍缩测试回 I2;
  OptTS×2 失败 (job57/58)。→ 若 P 修正后轮廓仍单调，申请 not_applicable。
  ★ e3 全链 blocked，等 P 重锚定。

## 下一步
1. species_P 重做（从 P_initial.xyz 或新构建，opt+freq + internal_coordinates 连通性验证）
2. e2 IRC（从 calc-53 鞍点）+ 端点身份验证
3. e1 NumFreq（calc-82 几何）
4. P 修正后: e3 IDPP I2→P(true) → OptTS/NumFreq 或 not_applicable 申请
5. thermochemistry 汇总 + RDS 能垒报告
