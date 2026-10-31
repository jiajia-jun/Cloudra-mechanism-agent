# P1b 四臂实验数据交付

2026-10-25归档更新；2026-11-01开放公开读取。原始运行包、历史复评分补充包与本次离线整理结果分别保存；文件名、大小和目录与 Drive 元数据核对。下列 SHA256 用于下载后的内容校验；Drive 接口未返回云端内容哈希。

[P1b Google Drive 数据目录](https://drive.google.com/drive/folders/1UIrzVTqZg8RofJcWX_dlhN-EoqpfkBjg)已纳入[Cloudra 公开研究数据目录](https://drive.google.com/drive/folders/1yZo3eJuCUuAgedQztgCtLyJcc8MZipf7)，持有链接即可读取和下载。本页与 [Gold 参考证据包](../../gold_compute/evidence/REPRODUCE.md)并列：Gold 包提供参考计算，本包保存 P1b 的实际 Agent 运行与复评分材料。

## 文件与校验值

| 文件 | 大小（字节） | 下载 | 内容 |
| --- | ---: | --- | --- |
| `cloudra-p1b-20261024-v2.tar.gz` | 2,436,379,132 | [下载完整包](https://drive.google.com/file/d/1EFYWbJFuDSSgHv12yGF0ntHIxoIaSwSU/view?usp=drivesdk) | 48 次运行的主归档；49,530 个普通文件、68,376 个归档成员，展开文件共 9,889,775,177 字节 |
| `cloudra-p1b-20261024-supplement.zip` | 11,479 | [下载补充包](https://drive.google.com/file/d/12JdoiLjiUpSlpRPu0P9Sl2nor6XLv16N/view?usp=drivesdk) | `RESCORED/` 下 4 份文件、2 份原始复评分脚本、README 与 SHA256 清单 |
| `cloudra-p1b-20261025-offline-results.zip` | 41,789 | [下载离线整理结果](https://drive.google.com/file/d/1iCNLRmEZZaO5gYwETrpBQFevkpqV7KGw/view?usp=drivesdk) | Standard 12 次结果、HA1/r2 人工恢复图、完整评分理由、来源与复现说明 |

[下载 SHA256 校验表](https://drive.google.com/file/d/1yStsru1pNe11B0ldXAOZd1lSpMRWBIJ3/view?usp=drivesdk)。文件继承公开目录的只读权限。

| 文件 | SHA256 |
| --- | --- |
| 主包 `.tar.gz` | `7a63841ab5eca6634da3ec5e98e6b95239c59abacd66e9659c9d082d2edb27c1` |
| 补充包 `.zip` | `0dc1851bb25784f78a37d4904b0578cdf5a1bc3b6477c71bb983a52c6b1cde11` |
| 离线整理结果 `.zip` | `4785b81f85a53e130dcfa941fc95709bc3450897260f1cbbf62dc80feb7ada08` |

48 次运行对应 `guided` / `record` / `standard` / `brief-errors` 四组，各含 `r1` / `r2` / `r3` 三轮，每轮为 `E1` / `NB1` / `HA1` / `IA1` 四题。归档完整不代表每次运行均通过科学验收，也不代表 50 题正式实验已经完成。

## 下载后校验与解压

将三个包下载到同一目录，在该目录执行：

```bash
shasum -a 256 -c <<'SHA256'
7a63841ab5eca6634da3ec5e98e6b95239c59abacd66e9659c9d082d2edb27c1  cloudra-p1b-20261024-v2.tar.gz
0dc1851bb25784f78a37d4904b0578cdf5a1bc3b6477c71bb983a52c6b1cde11  cloudra-p1b-20261024-supplement.zip
4785b81f85a53e130dcfa941fc95709bc3450897260f1cbbf62dc80feb7ada08  cloudra-p1b-20261025-offline-results.zip
SHA256

mkdir -p p1b-data p1b-supplement p1b-offline
tar -xzf cloudra-p1b-20261024-v2.tar.gz -C p1b-data
unzip cloudra-p1b-20261024-supplement.zip -d p1b-supplement
unzip cloudra-p1b-20261025-offline-results.zip -d p1b-offline
```

分数按版本区分：

- 主包根目录的 `SUMMARY.md`、`runs.csv` 和数据库是运行期原始快照。
- `RESCORED/results.csv` 与仓库中的[四臂重算明细](p1b_rescored_results.csv)是 2026-10-24 的 48 次历史离线评分，依据见[评分公平性修复](SCORING_FAIRNESS_FIXES.md)。
- **2026-10-25 的 Standard 更新见 [离线整理结果](p1b_offline_20261025/README.md)**：原交付物重评均分仍为 0.5344667；HA1/r2 人工恢复图后该项为 0.805，12 次均分为 0.6848833，科学自洽仍未通过。其他三组保留历史快照，不将本次局部更新称为全 48 次统一重评。

正式评估采用运行采集轨迹、离线统一整理并评分的口径；人工整理及字段来源需要记录，各组采用同一规则，不能按 Gold 补入本次运行没有的科学结论或证据。

随后按组别、轮次和题目查看原始运行、交付图与量化产物。历史补充包保留的 `rescore.py` 和 `compare_rescore.py` 硬编码工作站路径；此次 HA1/r2 的可移植复现步骤、评分器版本与路径迁移记录在新结果包中。
