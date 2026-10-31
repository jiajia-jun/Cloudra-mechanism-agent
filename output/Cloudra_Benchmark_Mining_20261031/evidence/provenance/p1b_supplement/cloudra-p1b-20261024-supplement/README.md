# Cloudra P1b 实验数据补充包（2026-10-24）

本包与主数据包 `cloudra-p1b-20261024-v2.tar.gz` 配套使用。主包保持原样，SHA-256：

`7a63841ab5eca6634da3ec5e98e6b95239c59abacd66e9659c9d082d2edb27c1`

## 数据范围

主包含 guided、record、standard、brief-errors 四臂，各三轮（r1–r3），每轮包含 E1、NB1、HA1、IA1 四题，共 48 个沙箱。该范围说明只确认归档内容齐全，不代表所有运行均通过科学验收。

## 使用哪份评分

采用 `RESCORED/results.csv` 的新评分，汇总见 `RESCORED/comparison.md`；评分器版本与修复依据分别见同目录下的 `SCORER_VERSION.md`、`SCORING_FAIRNESS_FIXES.md`。这些文件来自主包的 `RESCORED/`，本包仅单独收拢以便下载。

主包根目录的 `SUMMARY.md`、`runs.csv` 及各运行数据库保留原始评分快照，不能当作复评分后的结果。此次复评分针对原有沙箱离线进行，未重跑任务。

## 原始复评分脚本

`scripts/rescore.py` 与 `scripts/compare_rescore.py` 保留下载时的原始内容，未作修改。脚本硬编码了 `/home/ly` 下的工作站路径；在本机使用前需要按本地数据和环境位置调整。此次整理没有重新执行这两份脚本，没有运行评分或量子化学计算。

本补充包不包含旧补充数据库 `benchmark.db`。

## 文件校验

`SHA256SUMS.txt` 列出本包中 README、四份复评分文件和两份脚本的 SHA-256，路径相对于本包根目录。校验清单本身不列入自身哈希。
