# issue #33 复现材料（化学结构构建 / CREST 现场）

本目录是 GitHub issue #33 的**固定复现材料**：原始工具参数、输入结构、引擎逐字日志与
版本证据。用途是把"构建失败"与"CREST 本身失败"区分开，并为
`conformer_search` / `smiles_to_mol` / `qm_input_writer` 的共享结构构建回归测试提供输入。

复现环境与命令行见 `versions.txt`。

## 复现表

| # | 工具 / 用途 | 输入 | 关键参数 | 观察事实 | 判定 |
|---|---|---|---|---|---|
| 1 | `conformer_search(backend='crest')` 的等价前置流程 + `crest` | `[F-].CCl` (`fcl_ccl/`) | `-gfn2 --quick --chrg -1 --uhf 0` | 种子几何中 F–C 碎片间距离 **0.1392 Å**；CREST 退出码 1；stdout 打印 `Initial geometry optimization failed!`；写出空的 `NOT_CONVERGED`；无 `crest_conformers.xyz`；xTB 报 `|grad| > 500, something is totally wrong!`（gradient norm 649.03 Eh/a0，repulsion energy 89.42 Eh） | 已复现 |
| 2 | 同上 | `[O-]C=C.O.CC=O` (`enol_water_ald/`) | `-gfn2 --quick --chrg -1 --uhf 0` | 种子几何中碎片间 C–C 距离 **0.1157 Å**；CREST 退出码 1；同一 `Initial geometry optimization failed!` 标记；xTB 报 `|grad| > 500` | 已复现 |
| 3 | 对照：单分子 | `CCO` (`single_ref/`) | `-gfn2 --quick --chrg 0 --uhf 0` | 退出码 0，stdout 末行 `CREST terminated normally.`，`crest_conformers.xyz` 正常产出 | CREST 本身可用 |
| 4 | 判别假设 A：**独立 xTB 优化同一合法种子** | `fcl_ccl/input.xyz` (`xtb_standalone/`) | `xtb input.xyz --gfn2 --chrg -1 --uhf 0 --opt` | 退出码 1；`|grad| > 500, something is totally wrong!`；repulsion energy **89.416937579157 Eh**（与 CREST 内部 xTB 的 89.416948837702 Eh 同量级同结构） | 独立优化同样失败 ⇒ 缺陷在输入结构，**不在** CREST 的子引擎/参数/版本 |
| 5 | 同一组成但碎片已分离 | `[F-].CCl`，F–C 拉开到 3.0 Å（`topo_change/`） | `-gfn2 --quick --chrg -1 --uhf 0` | 出现 `Geometry successfully optimized.` 后接 `WARNING! Change in topology detected!` / `The topology change was seen in the initial geometry optimization.`；退出码 1；无 `crest_conformers.xyz`；现场留下 `xtbopt.log`（优化轨迹）、`struc.xyz`、`xtbtopo.mol` | 已复现：独立的第二类失败（初始拓扑变化），与失败 #1/#2 不同类 |

**对照 #3 的作用**：同一台机器、同一 CREST/xTB 版本、同一命令行模板下，单分子体系正常
完成。因此 #1/#2 的失败**不是** CREST 安装、版本或执行环境问题，而是喂给 CREST 的初始
结构本身不可用。

## 观察事实与根因假设分开记录

**观察事实（可复算，见上表与逐字日志）**

- 两个失败输入的关键碎片间接触距离分别为 0.1392 Å 与 0.1157 Å。
- issue #33 报告的 0.139 Å 与本目录 `fcl_ccl` 实测的 F–C 距离 0.1392 Å 一致；
  这是**单一输入的实测值**，不作为"跨随机种子必然重现"的断言（种子变化会改变叠放的具体
  距离，但不会消除叠放本身）。
- CREST 的失败发生在 **初始几何优化**阶段，早于构象搜索 / CREGEN：
  stdout 只有 `Initial geometry optimization failed!`，`crest_conformers.xyz` 从未生成。
- 两个失败用例的底层 xTB 错误都是**优化器梯度爆炸**（`|grad| > 500`），不是 SCF 不收敛、
  不是电子态输入被拒。上表第 5 行是**另一类**失败（初始拓扑变化），与它们不同类。

**根因假设（尚未被 Task 2/4 之外的证据确证，不得当作结论）**

- 假设 A：`conformer_search(backend='crest')` 的 SMILES → 3D 前置分支
  （`AddHs` → `EmbedMolecule(ETKDGv3)` → `MMFFOptimizeMolecule`）没有任何碎片间
  去重叠处理，而 ETKDG 对多碎片体系逐碎片独立嵌入并随机摆放，因此碎片可以整体互穿。
  同一文件的 RDKit 后端分支已有 `_resolve_overlap` / `_separate_fragment_centroids`，
  但该修复**没有**覆盖 CREST 分支，也没有覆盖 `smiles_to_mol` 与 `qm_input_writer`。
- 假设 A 已被上表第 4 行**支持**（独立 xTB 对同一种子同样失败 ⇒ 结构本身不可用），
  但"ETKDG 会互穿"的完整机制仍须由 Task 2 的共享构建器回归测试确立；
  "点号拆分 + 逐组分构建"是否足够由 Task 2 的测试回答，本文件不作断言。
- **待排查项**：`AllChem.MMFFOptimizeMolecule` 对含 F⁻ 的体系返回 0（"已收敛"），但该几何
  仍处于互穿状态——力场优化**不构成**碎片已分离的证据。此点在 Task 2 中以"优化成功不等于
  几何可用"的显式状态暴露，不允许再用"坐标已生成/优化返回 0"冒充构建成功。

## 引擎能力核对（Task 4 前置事实）

用 `strings` 读取本机 CREST 二进制（2.12）的选项表与提示文本，并用 `-dry` 实跑确认解析器接受：

- `--noreftopo` **在本机 2.12 版本中存在且被解析器接受**：`crest input.xyz -gfn2 --quick
  --chrg -1 --uhf 0 --noreftopo -dry` 返回码 0、末行 `STOP normal dry run termination.`。
  它**未出现在 `crest --help` 的选项清单里**（`--help` 只列了 `-notopo`：turn off any
  topology checks in CREGEN），但二进制内的提示文本原文把它列为官方出口之一：
  `B) Restart the same CREST call as before, but ignore the topology change   by using
  the "--noreftopo" keyword. (May produce artifacts)`。
  ⇒ 采用 `--noreftopo` 的依据是该二进制自身提示文本，不是猜测的旗标。
- `-nci`（NCI 模式：在输入结构周围生成椭球势并加进 MTD 模拟）在本机 2.12 中存在。
- 分类用的逐字标记（取自本机二进制字符串表，并经上表实跑验证）：

  | 类别 | 逐字标记 |
  |---|---|
  | 初始优化失败 | `Initial geometry optimization failed!` |
  | 初始拓扑变化 | `WARNING! Change in topology detected!` |
  | 正常完成 | `CREST terminated normally.` |
  | 异常终止 | `abnormal termination of crest` |
  | 搜索阶段失败 | `Trial MTD ` … `did not converge!`；`Warning: MD seemingly failed (no xtb.trj)`；`Automatic xtb restart failed ` |

  这些标记一律用**精确整行/token 比对**识别（`crest_runner` 内不引入正则）。

## 文件说明

- `<case>/input.xyz` — 逐字保存的、当时交给 CREST 的输入坐标（Task 1 要求保留原始输入结构）。
- `<case>/command.txt` — 实际执行的 CREST 命令行。
- `<case>/crest_stdout.log` — `crest` 的完整 stdout 逐字原文。
- `<case>/xtb_tail.log` — 底层 `xtb.out` 的逐字尾部（含 `SUMMARY` 段与 `[ERROR]` 块）；
  仅失败用例具备。CREST 自己写出的 `xtb.out` 完整内容体积过大且其余部分不含分类所需标记，
  因此只保留判定所依据的逐字片段。
- `xtb_standalone/xtb_stdout.log` — 用独立 xTB（不经 CREST）优化 `fcl_ccl/input.xyz` 的完整
  stdout 逐字原文，用于上表第 4 行的假设判别。
- `topo_change/` — 上表第 5 行的输入与现场：`input.xyz`、`crest_stdout.log` 全文、
  `xtbopt_trajectory_head.log`（CREST 留下的 `xtbopt.log` 优化轨迹开头若干帧，用于观察
  初始优化过程中发生了什么拓扑变化；只记录，不判定该变化是否允许）。
- `versions.txt` — CREST / xTB / ORCA / RDKit 版本与命令行（工具输出，不含密钥与环境变量）。

## 未复现项

- 本目录**不包含** issue #33 报告者原始会话里的工具调用参数与结果文本：这些材料不在本
  仓库内，且无法在不推测的前提下重建。issue 中除 0.139 Å 之外的具体数值一律**标记为未复现**，
  不得用本目录的实测值替代，也不得写进测试断言。
- 未复现项：报告者所使用的 CREST/xTB 版本号、其原始 SMILES 之外的输入、以及其会话中的
  工具返回 JSON。上表第 1/2 行的失败是**本机独立复现**，与报告者证据同因但非同源。
