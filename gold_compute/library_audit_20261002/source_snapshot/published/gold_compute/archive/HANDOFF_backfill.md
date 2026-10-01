# HANDOFF — gold 能垒回填（back-fill）到题源

状态：DONE。源文件已改 → 生成器已重跑 → \`uv run pytest -q tests/test_benchmark.py\` = **136 passed, 5 warnings**（exit 0）。

## 目标
把本战役 computed 逐边能垒回填到 **题源**（easy.md / normal_registry / hard_registry），重跑生成器刷新 ideapool/tasks/*.json，守卫绿。禁止手改 ideapool/tasks/*.json 与 gold_compute/**。

## 逐题逐边（源文件:行 → 旧值 → 新值）
| 题(tier) | edge | 源文件:行 | 旧→新 |
|---|---|---|---|
| F1 (easy) | F1_E1 | ideapool/reaction_candidates/easy.md:71 | 39.4 → 39.36 |
| NU5 (normal) | NU5_E1 | cloudra/benchmark/normal_registry/ru.py:54 | (缺键/None) → 0.0 |
| NU5 | NU5_E2 | ru.py:60 | 19.9 → 8.2 |
| NU5 | NU5_E3 | ru.py:67 | 16.6 → 0.0 |
| NU5 | NU5_E4 | ru.py:74 | 13.8 → 31.7 |
| NA5 (normal) | NA5_E1 | cloudra/benchmark/normal_registry/ai.py steps[0] | None（保持缺键） |
| NA5 | NA5_E2 | ai.py:64 | (缺键/None) → 13.94 |
| NA5 | NA5_E3 | ai.py:70 | (缺键/None) → 69.94 |
| NA5 | NA5_E4 | ai.py:76 | 8.9 → 3.37 |
| NA5 | NA5_E5 | ai.py steps[4] | None（保持缺键） |
| HA6 (hard) | HA6_E1 | cloudra/benchmark/hard_registry/ab.py:51 | (缺键/None) → 31.24 |
| HA6 | HA6_EM1 | ab.py:59 | (缺键/None) → 42.31 |
| HL1 (hard) | HL1_E1 | cloudra/benchmark/hard_registry/jl.py:27 | (缺键/None) → 0.0 |
| HL1 | HL1_E2 | jl.py:33 | 39.9 → 23.13 |
| HL1 | HL1_E3 | jl.py:~39 | 18.0(+w0.5) → 键删除(None) |
| HL1 | HL1_E4 | jl.py steps[3] | None（保持） |
| HL1 | HL1_E5 | jl.py:~49 | 30.5(+w0.5) → 键删除(None) |
| HG2 (hard) | HG2_E1 | cloudra/benchmark/hard_registry/fgk.py:58 | (缺键/None) → 29.67 |
| HG2 | HG2_EM1 | fgk.py:66 | (缺键/None) → 26.39 |
| L1 anchor (hard) | — | ideapool/reaction_candidates/hard.md:136 | ΔE‡≈39.9 → 23.13（anchor='barrier' 一致性强制） |

**未改（源值已与 computed 一致）**：NU3(1.7/55.81/23.76)、NU6(2.66/15.72)、NY3(15.5/12.5/0.0)、HA1(33.04/38.76)。

## 关键决定 / 异动
1. hard.md L1 能垒格被改：gen_hard_tasks 对 anchor="barrier" 强制 题源格值 == max(registry 逐边)，E2 改 23.13 后必须同步格值；文献值 39.9(Yamabe 2005) 保留在括号内。
2. null 边表示法：沿用该库既有写法 = 步字典**缺 'barrier' 键**（生成 → barrier_kcal_mol: null）。故 HL1_E3/E5 删除 barrier+weight；NA5_E1/E5 保持缺键。
3. HL1_E4 subsumed/None（computed edges 亦为 null），未动。
4. **HG2 channel/favored 标签存在内部矛盾（需注意）**：computed HG2.json 中 edge HG2_E1→syn 产物但 channel="boat_ts"/favored=false、barrier 29.67；HG2_EM1→anti 产物但 channel="chair_ts"/favored=true、barrier 26.39。task JSON 的 E1↔syn、EM1↔anti 由生成器固定且与 computed 的 "to" 一致，故按 edge-id 回填无误；但计算表明 anti(26.39) 反而更低／被标 favored，与 registry 主线 chair↔syn 的能垒高低相反。仅回填 barrier，未改 channel/favored，请复核该科学归属。

## 生成器重跑
\`uv run python -m cloudra.benchmark.gen_easy_tasks\` → 20 tasks；gen_normal_tasks → 10；gen_hard_tasks → 10。
刷新文件：ideapool/tasks/easy/F1.json, normal/{NU5,NA5}.json, hard/{HA6,HL1,HG2}.json（生成器写出，非手改）。

## 验证
\`uv run pytest tests/test_benchmark.py -q\` → **136 passed, 5 warnings in 8.21s**（含 test_easy/normal/hard_tasks_regenerate_identically 全绿）。

## 环境备注
本机 \`uv\` 在 ~/.local/bin（默认 PATH 未含）；运行需 \`export PATH="$HOME/.local/bin:$PATH"\`。
