# gold_compute/ — gold 参考答案补齐战役目录

目标：为 benchmark 题库补齐/核实 `gold` 参考答案，使每题都有可用的参考能垒。

**2026-09-13 计划变更（用户决策）**：参考值改为**文献调研填充**（不跑计算）。
原计划「MACE-OMol25 自算标定」因 OptTS/IRC 链路卡住而落空；现改为「文献锚点」路线，
产物 `verification` 按文献核实强度记 verified/partial/unverified，不再要求
`computed_by_us=True`。

## 口径（必须对齐生成器）
- 能垒基准 `central_complex`（TS 相对反应物/离子-偶极络合物）；文献值为分离反应物
  渐近线 / 微溶剂化 / 溶液自由能等其它口径时，在单元格括号内注明，并在生成器的
  `_BARRIER_FRAME_UNVERIFIED` 登记，verification 降 unverified。
- 能垒类型按题定义（Ea/ΔE‡/ΔH‡/ΔG‡），源未注明时保持 None（诚实缺测）。
- 数值 + 类型 + 出处 DOI 写回**题源 md** 的「gold 能垒锚点」列，再重跑对应生成器
  （`test_*_tasks_regenerate_identically` 守卫同步）。生成器是题库唯一事实来源。

## 题源与回填路径
- easy：`ideapool/reaction_candidates/easy.md` → `gen_easy_tasks.py` → `ideapool/tasks/easy/*.json`
- normal：`ideapool/reaction_candidates/normal.md` → `gen_normal_tasks.py` → `ideapool/tasks/normal/*.json`
- hard：`ideapool/reaction_candidates/hard.md` + `cloudra/benchmark/hard_registry/*.py`(anchor) → `gen_hard_tasks.py`

## 待办清单（2026-09-13）
- normal 缺数值锚点（9）：NA2 NA5 NI1 NO3 NR1 NU3 NU5 NU6 NY3
- hard 缺数值锚点（2）：HD2 HL1（注册表 anchor 需 None → "barrier"）
- hard 选择性锚点（ΔΔ，已有值，7）：HA1 HA6 HE2 HE3 HF1 HG2 HI1（绝对能垒不在本战役范围）
- easy 待复核（10）：C3 D1 D3 D4 F1 G2 G3 M1 M16 M8

## 产出约定
每题一条：barrier_kcal_mol / barrier_type / frame / DOI / verification / method 一句话
依据；汇总后统一回填题源 md，重跑生成器并断言守卫通过。
