# P2 正式实验数据交付

归档版本：`Cloudra-P2-final-20261031-FULL`。登记日期：2026-11-01。

[Cloudra 公开研究数据目录](https://drive.google.com/drive/folders/1yZo3eJuCUuAgedQztgCtLyJcc8MZipf7)集中保存 P2 正式实验、P1b 重复实验、Gold 参考证据、行为与激活原始档案和 SI 配套复现材料，权限为“持有链接的任何人／查看者”。

## P2 完整归档

- 文件：`Cloudra-P2-final-20261031-FULL.tar.gz`
- 文件大小：14,915,315,627 字节（14.915 GB），已与云端核对。
- 实验范围：50题、四种配置、200次保留运行。
- 包内 README 生成时间：`2026-10-31T17:28:18+08:00`；归档代码快照：`master 0961d9ab`。
- 归档含195,453个普通文件，文件逻辑总量48,488,766,289字节（约48.5 GB）；其中195,411个文件位于`campaign_data/`。
- 本地整包 SHA256：`dfd3fe8f71f236b8bc463ad1753d05bdf89aee44be9b11dbe9a2bce43b9c3155`
- 本地整包 MD5：`c16b4e6ada0e92d2a41e3363050b0e57`
- 上传状态：已完成；[直接下载完整归档](https://drive.google.com/file/d/1DXtlUEmhshADrG48fyZLkEuqNxFWOTFM/view?usp=drivesdk)，已验证公开只读权限。

## 完整包目录与用途

| 目录或文件 | 用途 |
| --- | --- |
| `campaign_data/cloudra-p2b-20261025/` | 3次保留运行的原始实验目录。 |
| `campaign_data/cloudra-p2c-20261025/` | 197次保留运行的原始实验目录。 |
| 各实验目录内的分臂记录 | `benchmark.db` 保存运行期评测记录；`sandboxes/<TASK>/` 保存原生计算日志、`PROCESS`、`REPORT` 与机理图。 |
| `runtime/runtime-v2.db`、`compute.db` 与配置快照 | 保存运行轨迹、计算账本与当时的运行设置。 |
| `campaign_data/SHA256SUMS_DBS.txt`、`campaign_data/DIRS.txt` | 数据库校验表与原始实验目录清单。 |
| `tables/`、`runs/` | 正式结果表、逐次运行分数和运行期原始评分记录。 |
| `reconstructions/`、`docs/` | 离线恢复图、字段来源、方法说明与评分修复记录。 |
| `reports/`、`MANIFEST.txt`、`SHA256SUMS` | 配套分析、发布文件目录与校验表。 |

正式得分采用离线整理后的发布表；原始运行数据库保留运行期记录。各目录的具体内容及来源按包内 README 和清单读取。

## SI 配套复现包

[公开下载 `Cloudra_SI_Data.zip`](https://drive.google.com/file/d/1lXNR6zhWTP2kJ1B5_-A9elXmblQX5ALf/view?usp=drivesdk)，18,969,168 字节（约19.0 MB），已于2026-11-02原位更新，下载链接不变。该包保存50题任务定义、200次正式运行的完整精度评分表、行为实验与激活记录、文献登记，以及出版表格和配图的独立复现脚本；解压得到 `companion_data/`。包内 `file_manifest.json` 提供逐文件大小与 SHA256。当前 ZIP 的 SHA256 为 `93f551bba698bbeadad64646789ce269378b57ce4e8db2cbb737f23d90c474a5`；公开目录中的校验清单已同步。

## 行为实验与激活原始档案

[公开下载第三章完整原始档案](https://drive.google.com/drive/folders/1Zkn6_2aDlloAe-bmfd7w27zxmQKj5L9K)：3个ZIP分别为60,639,211、52,035,252和52,033,587字节，合计164,708,050字节（164.7 MB）。目录同时提供 README、文件索引与校验材料，保存正文行为诊断与激活干预对应的完整原始记录，并与精简 SI 复现包配套使用。

## 其他公开数据

- [P1b重复实验：48次运行、历史复评分和离线整理结果](P1B_DELIVERY.md)。
- [Gold参考计算证据：版本、逐文件清单与校验](../../gold_compute/evidence/REPRODUCE.md)。

## 下载与解压

在公开目录下载 P2 完整归档后，先校验再解压。macOS 命令如下；Linux 可将 `shasum -a 256` 换为 `sha256sum`。

```bash
shasum -a 256 -c <<'SHA256'
dfd3fe8f71f236b8bc463ad1753d05bdf89aee44be9b11dbe9a2bce43b9c3155  Cloudra-P2-final-20261031-FULL.tar.gz
SHA256

mkdir -p cloudra-p2-data
tar -xzf Cloudra-P2-final-20261031-FULL.tar.gz -C cloudra-p2-data
```

上述哈希来自本地完整归档，供下载后校验。云端文件大小与本地一致，公开只读权限已通过Drive元数据核实。包内容统计见公开目录中的 `P2_PACKAGE_INVENTORY.json`。

<a id="rescore-archived-deliveries"></a>

## 用归档交付物重新评分

完整包里的 `campaign_data/` 保存 200 次保留运行的沙箱，`reconstructions/<分组>/<题号>/mechanism_graph.json` 保存事后整理的机理图。下面的命令把这些已经整理好的交付交给当前仓库的 `BenchmarkRunner.score_sandbox`，写出图结构、自洽性、准确度和综合分。Agent 和量化计算都不启动。SI 配套包继续根据已有 CSV 重绘表格和图；包内 `evaluation_records/reproduce_f4.py` 仍只重评四次 F4。全表入口是本页这条命令。

输出目录要放在归档外面。程序只在需要换上整理图，或把工作站绝对证据路径改写为沙箱内已有文件时，才在输出目录做一份暂存。同一文件系统上用硬链接，不复制原生日志；输出目录因此最好和归档放在同一块磁盘上。归档中的原文件保持不动。

在仓库根目录执行。`--p2-root` 可以是解压得到的 `Cloudra-P2-final-20261031`，也可以是它的上一级。

```bash
.venv/bin/python -m cloudra.benchmark.rescore_archive \
  --p2-root cloudra-p2-data/Cloudra-P2-final-20261031 \
  --output /tmp/p2-rescore \
  --apply-target-overlay
```

命令读取包内 `tables/final_scores_per_run.csv` 的保留运行，并把表里的工作站沙箱路径定位到 `campaign_data/<campaign>/...`。整理图存在时，这次评分使用整理图；否则使用沙箱里的原生 `mechanism_graph.json`。图中写成绝对路径、且该文件已经在本沙箱内的证据，改写成相对路径。对不上现有文件的路径保持原样，程序不补造日志。

默认任务定义是本仓库的 `ideapool/tasks`。当前版本这 50 个文件与 SI 配套包 `task_definitions/` 逐字节相同。结果写到输出目录的 `rescored_runs.csv` 和 `rescored_runs.json`。`sandbox` 是归档内的保留沙箱，`reconstruction` 标明是否使用了整理图。`graph_score`、`selfconsistency_score`、`accuracy_score`、`final_score` 是图结构、自洽性、准确度和综合分。`scorer_accuracy` 与 `scorer_final` 始终保留本次 `score_sandbox` 的原始准确度和综合分。

2026-11-02 的目标对应后处理记录在 `paper/overleaf/Cloudra_SI/companion_data/revision_20261102/target_matching/`。正式表 `cloudrabench_200_run_scores.csv` 对下面五行采用了校正表中的准确度和综合分，图结构和自洽分仍是整理评分时记下的值：

| 分组 | 题号 |
| --- | --- |
| standard | L2 |
| guided | IA5 |
| record | IA5 |
| brief-errors | IA5 |
| brief-errors | IC3 |

当前仓库的准确度实现和任务定义已经包含这次后处理。整理图和原生日志与归档一致时，`score_sandbox` 可以直接给出这五行的正式准确度。综合分仍可能与正式表不同，因为正式综合分用的是当时记录的图结构和自洽分，而这次命令报告的是当前评分器算出的图结构和自洽分。`--apply-target-overlay` 把校正表 `target_matching_accuracy_corrections.csv` 里的准确度和综合分原样抄入这五行，不重新计算分数；其它运行保持评分器输出。省略该参数时，表中全部是本次评分器的结果。换一份校正表时使用 `--target-overlay`。

只重评一次保留运行：

```bash
.venv/bin/python -m cloudra.benchmark.rescore_archive \
  --p2-root cloudra-p2-data/Cloudra-P2-final-20261031 \
  --output /tmp/p2-f4-rescore \
  --only standard/F4
```

P1b Standard 的 12 次运行可以一起重评。主包提供沙箱，离线整理包提供 HA1/r2 的机理图。未写 `--p1b-offline` 时使用仓库里的 [离线整理结果](p1b_offline_20261025/README.md)，内容与公开 zip 相同。离线 zip 本身没有沙箱。

```bash
.venv/bin/python -m cloudra.benchmark.rescore_archive \
  --p2-root cloudra-p2-data/Cloudra-P2-final-20261031 \
  --p1b-root /path/to/cloudra-p1b-20261024 \
  --output /tmp/archive-rescore \
  --apply-target-overlay
```

没有完整归档时，入口本身用夹具检查：

```bash
.venv/bin/python -m pytest tests/test_benchmark_rescore_archive.py
```

P1b 离线表记录的单次读日志耗时从数秒到大约两分钟。P2 的 200 次是同样的只读评分，耗时随沙箱里的原生日志变化。本命令不代替 SI 配套包里的作图脚本。
