# P1b 四臂实验数据交付

2026-10-25。归档完整性已核对，两个包均已上传；文件名、大小、目录和私有权限已与 Drive 元数据核对。下列 SHA256 用于下载后的内容校验；Drive 接口未返回云端内容哈希。

[Google Drive 数据目录](https://drive.google.com/drive/folders/1UIrzVTqZg8RofJcWX_dlhN-EoqpfkBjg)（私有，下载需要文件访问权限，未公开分享）。本页与 [Gold 参考证据包](../../gold_compute/evidence/DELIVERY.md)并列：Gold 包提供参考计算，本包保存 P1b 的实际 Agent 运行与复评分材料。

## 文件与校验值

| 文件 | 大小（字节） | 下载 | 内容 |
| --- | ---: | --- | --- |
| `cloudra-p1b-20261024-v2.tar.gz` | 2,436,379,132 | [下载完整包](https://drive.google.com/file/d/1EFYWbJFuDSSgHv12yGF0ntHIxoIaSwSU/view?usp=drivesdk) | 48 次运行的主归档；49,530 个普通文件、68,376 个归档成员，展开文件共 9,889,775,177 字节 |
| `cloudra-p1b-20261024-supplement.zip` | 11,479 | [下载补充包](https://drive.google.com/file/d/12JdoiLjiUpSlpRPu0P9Sl2nor6XLv16N/view?usp=drivesdk) | `RESCORED/` 下 4 份文件、2 份原始复评分脚本、README 与 SHA256 清单 |

[下载 SHA256 校验表](https://drive.google.com/file/d/1yStsru1pNe11B0ldXAOZd1lSpMRWBIJ3/view?usp=drivesdk)。主包、补充包及目录权限均仅所有者。

| 文件 | SHA256 |
| --- | --- |
| 主包 `.tar.gz` | `7a63841ab5eca6634da3ec5e98e6b95239c59abacd66e9659c9d082d2edb27c1` |
| 补充包 `.zip` | `0dc1851bb25784f78a37d4904b0578cdf5a1bc3b6477c71bb983a52c6b1cde11` |

48 次运行对应 `guided` / `record` / `standard` / `brief-errors` 四组，各含 `r1` / `r2` / `r3` 三轮，每轮为 `E1` / `NB1` / `HA1` / `IA1` 四题。归档完整不代表每次运行均通过科学验收，也不代表 50 题正式实验已经完成。

## 下载后校验与解压

将两个文件下载到同一目录，在该目录执行：

```bash
shasum -a 256 -c <<'SHA256'
7a63841ab5eca6634da3ec5e98e6b95239c59abacd66e9659c9d082d2edb27c1  cloudra-p1b-20261024-v2.tar.gz
0dc1851bb25784f78a37d4904b0578cdf5a1bc3b6477c71bb983a52c6b1cde11  cloudra-p1b-20261024-supplement.zip
SHA256

mkdir -p p1b-data p1b-supplement
tar -xzf cloudra-p1b-20261024-v2.tar.gz -C p1b-data
unzip cloudra-p1b-20261024-supplement.zip -d p1b-supplement
```

先读补充包 README；**新评分以 `RESCORED/results.csv` 为准**，评分修改依据见[评分公平性修复](SCORING_FAIRNESS_FIXES.md)，仓库中的[重算明细](p1b_rescored_results.csv)便于直接查阅。主包原有 `SUMMARY.md`、`runs.csv` 及数据库保留旧评分快照，不能与新评分混用。

随后按组别、轮次和题目查看原始运行、交付图与量化产物。补充包保留 `rescore.py` 和 `compare_rescore.py` 原件；脚本硬编码工作站路径，此次整理未修改或运行脚本，换机器使用前须先核对依赖、代码版本与路径。
