# QM 一致性审计复现材料（2026-10-19）

主报告：[Gaussian / ORCA 功能一致性审计](../../archive/2026-10-19-qm-consistency-audit.md)。源码基线为 `42eda2401df5295b46a07031f805f021286f1e82`；[source-chain.md](source-chain.md) 是归档时的完整局部调用链源码快照，包含本轮已修复的 paired charge 行，不是后续必须同步维护的实现文档。

这里是诊断探针，不是新增测试承诺。退出 0 表示脚本完成取证；多个脚本故意打印当前缺陷或捕获异常，因此退出 0 不代表功能通过。没有真实 Gaussian / ORCA、LLM 或整题 easy 运行。

## 执行

使用已安装 `dev` / `chem` 依赖的项目 Python，在仓库根目录运行：

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/cloudra_qm_unit_roundtrip_audit.py
```

将末尾文件名换成下表脚本即可。脚本按自身位置找到仓库，支持从其他 cwd 以绝对路径执行；它们先切换到新建的 `/tmp` 工作目录，再导入 Cloudra。配置、数据目录、临时输入、生成材料和 dry-run 替身均位于 `/tmp`，禁止写入导入模块的 bytecode，不读取仓库 `.env` 或用户 YAML 配置。脚本保留原探针的判定逻辑，仅调整了入口定位、临时目录隔离和导入格式。

| 脚本 | 对应结果 | 材料与动作 |
| --- | --- | --- |
| [cloudra_qm_unit_roundtrip_audit.py](cloudra_qm_unit_roundtrip_audit.py) | [units.txt](outputs/units.txt) | 手工明确声明的 1 Å H2 结构；公开 writer 和 native 读回，不运行 QM |
| [probe_writer_fchk.py](probe_writer_fchk.py) | [fchk.txt](outputs/fchk.txt) | 明确声明的 water XYZ；公开 writer，检查 Link0 完整性 |
| [irc_verify_audit.py](irc_verify_audit.py) | [gaussian_termination.txt](outputs/gaussian_termination.txt) | 已捕获 HCN Gaussian IRC 副本；TS / 端点为合成 parser fixture，只改 IRC 终止标记 |
| [orca_irc_verify_audit.py](orca_irc_verify_audit.py) | [orca_termination.txt](outputs/orca_termination.txt) | native-shaped ORCA parser fixture，只改 IRC 终止标记 |
| [ts_native_dependency_audit.py](ts_native_dependency_audit.py) | [readfc.txt](outputs/readfc.txt) | 合成 checkpoint / Hessian 字节，仅检查依赖传输；临时 `g16` spy 故意退出 42，不产生原生成功日志 |
| [cloudra_irc_neighbor_manifest_probe.py](cloudra_irc_neighbor_manifest_probe.py) | [neighbor_manifest.txt](outputs/neighbor_manifest.txt) | 原生 HCN IRC 的两个副本；第二份只附加换行，实际 snapshot 生成第一份 manifest |
| [cloudra_orca_foreign_sidecars_probe.py](cloudra_orca_foreign_sidecars_probe.py) | [foreign_sidecars.txt](outputs/foreign_sidecars.txt) | HCN IRC 缺自身侧车；放入不同 NU3 作业的真实侧车，检查归属及 snapshot |
| [cloudra_unrelated_parse_failure_probe.py](cloudra_unrelated_parse_failure_probe.py) | [malformed_candidate.txt](outputs/malformed_candidate.txt) | 合格基线旁加入未绑定合成坏日志，把一个坐标改成 `**************` |
| [gaussian_irc_print_semantics_audit.py](gaussian_irc_print_semantics_audit.py) | [gaussian_irc_print_semantics.json](outputs/gaussian_irc_print_semantics.json) | 只读比较已捕获 HCN Euler-PC 的 Input / CURRENT 数值，JSON 写到 `/tmp` |
| [e1_gaussian_print_semantics_audit.py](e1_gaussian_print_semantics_audit.py) | [e1_gaussian_print_semantics.json](outputs/e1_gaussian_print_semantics.json) | 只读比较外部 E1 原件的 corrected CURRENT、Opt 输入和原生日志首帧；必须显式传入绝对路径 |
| [cloudra_e1_native_replay.py](cloudra_e1_native_replay.py) | [e1_native_replay.json](outputs/e1_native_replay.json)、[stdout](outputs/e1_native_replay.txt) | 读取并校验外部 E1 包，复制到 `/tmp`，真实 proposal → species → 原入参 step 提交；不恢复原审批状态、不写原件 |

E1 专用探针不带入约 14 MB 的原件，也没有硬编码某次解包目录：

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/e1_gaussian_print_semantics_audit.py /absolute/path/to/extracted/evidence/e1-irc-20261019/calc
.venv/bin/python docs/evidence/qm_consistency_20261019/cloudra_e1_native_replay.py /absolute/path/to/extracted/evidence/e1-irc-20261019
```

原件来源：临时证据分支 `evidence/e1-irc-20261019`、commit `4f26105257d292deca0de0c3a8b434d2b8842b0d`，解包后需先核对其 `SHA256SUMS`。另保留 [e1_native_replay.json](outputs/e1_native_replay.json)，包含当时调用回执和独立共享 verifier 的复核；原 agent 的机理描述只是历史声明，不作为本报告科学结论。

`outputs/` 保存归档前独立重跑的输出；归档时仅清理终端告警行末空白，未改动数值、JSON 或科学日志原件。临时目录名、对象地址和 traceback 行号是当次执行事实，重跑会变化；可选 cclib 对合成节选的告警按原样保留。判断结论时应读取最终结构化结果及主报告的边界说明。

## 材料真实性与范围

- 实际捕获日志和侧车保留在已有 `tests/fixtures/`，本目录不复制或改写原件。
- 合成 native-shaped 材料仅验证解析、参数传递、归属和异常边界，不声称具有计算得到的能量、驻点或真实机理。
- 配对 IRC 电荷修复的四例 red-green 回归位于 `tests/test_irc_separated_products.py`；本目录不再复制一套测试逻辑。
- E1 原件已确认 corrected CURRENT → 实际 Opt 起点断链，完整 DAG 科学提交路径也已复现原返回；原 DAG 数据库未提供，不恢复原审批／skipped 状态。本目录的 HCN 对照不替代 E1 原件，也不授权放宽几何 tolerance。

入口检查：

```bash
PYTHONPYCACHEPREFIX=/tmp/cloudra-audit-pycache .venv/bin/python -m compileall -q docs/evidence/qm_consistency_20261019
.venv/bin/ruff check docs/evidence/qm_consistency_20261019
```
