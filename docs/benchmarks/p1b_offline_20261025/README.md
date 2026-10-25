# P1b Standard：离线整理与重评分

2026-10-25。运行阶段采集研究轨迹与原始计算产物，正式评估在离线整理后完成。原来的四臂 48 次评分保留为[历史快照](../p1b_rescored_results.csv)；本次只重评 Standard 的 12 次运行，并从其中 HA1 第 2 轮已有记录恢复缺失的机理图。

## 本次结果

| 项目 | 原交付物重评 | 人工离线还原后 |
| --- | ---: | ---: |
| Standard / r2 / HA1 综合分 | −1.0000 | **0.8050** |
| Standard 12 次综合均分 | 0.5344667 | **0.6848833** |

| HA1 / r2 分项 | 分数 |
| --- | ---: |
| 图结构 | 1.0000 |
| 自洽性 | 0.3500 |
| 准确度（优势产物定性选择性） | 1.0000 |

反应物、E/Z 两个产物极小值和两个一阶鞍点来自本次运行的原生日志。两个候选通道的电子能垒为 33.0918 与 38.8086 kcal/mol，较低者被标为优势通道。**两条通道都没有完整的 IRC 连接证明，科学自洽验收仍未通过。** 部分得分不代表机理已完整确证。

原始运行未生成 `mechanism_graph.json`。补图是本次离线整理产物，来源逐字段记录在 [reconstruction_notes.txt](reconstruction_notes.txt)。本次没有增加模型运行或量化计算，也没有修改原生日志。

## 评估口径

1. 运行阶段保存对话、工具调用、报告、原始输入和计算产物；现有程序附带的即时分数作为诊断快照。
2. 离线阶段从该次运行已留下的内容还原统一机理图，再交给同一评分器。允许恢复缺失 JSON、修复搬移后的文件引用及按既定公式换算已有数值。
3. 人工整理及字段来源需要记录；不能根据 Gold 补入原轨迹没有的结论、通道或计算证据。无法确定的信息保留未知，科学验收标准不变。
4. 各组使用同一整理规则。本次是事后离线再分析；其余三组仍为 2026-10-24 快照，不能把这些快照与本次局部更新称为全 48 次统一重评后的正式比较。

完整口径见 [protocol.txt](protocol.txt)。本次更新是评估方法与结果交付，运行程序的即时评分和基础交付约束仍按当前实现执行。

## 文件

| 文件 | 内容 |
| --- | --- |
| [standard_results.csv](standard_results.csv) | 12 次结果；`offline_reconstruction` 标明 HA1/r2 为人工还原，其余使用原图 |
| [standard_original_graph_results.csv](standard_original_graph_results.csv) | 同一版本对 12 次原交付物的重评分，与历史综合分一致 |
| [ha1_r2_graph.json](ha1_r2_graph.json) | 5 节点、2 候选边的人工离线机理图，原生证据路径均为相对路径 |
| [ha1_r2_score.json](ha1_r2_score.json) | 补图后的完整分项和评分理由 |
| [summary.json](summary.json) | 前后分数、组均分和原生日志 SHA256 |
| [scorer_version.json](scorer_version.json) | 评分器提交、原始包校验值与适用范围 |
| [path_relocations.json](path_relocations.json) | IA1/r2 七条旧工作站绝对引用的路径迁移记录 |

CSV 的 `undelivered` 沿用当前评分器对 `.cloudra/mechanism_evidence.json` 是否存在的标记；该标记本身不扣综合分，也不等于机理图缺失。`selfconsistency_score` 为连续分，`selfconsistency_passed` 为完整科学自洽验收结果。`seconds` 是本机离线评分耗时，不是研究运行成本。

## 复现 HA1 / r2

先按 [P1b 交付说明](../P1B_DELIVERY.md)还原主包。以下在仓库根目录运行，参数分别为已解压的 `cloudra-p1b-20261024` 目录与一个尚不存在的输出目录；示例将原沙箱复制后放入离线机理图。

```bash
.venv/bin/python - /path/to/cloudra-p1b-20261024 /tmp/p1b-ha1-replay <<'PY'
import json
import shutil
import sys
from dataclasses import asdict
from pathlib import Path

from cloudra.benchmark.runner import BenchmarkRunner
from cloudra.benchmark.schema import TaskSpec
from cloudra.runtime_v2.schemas import OrchestrationMode

data, out = map(Path, sys.argv[1:])
source = data / "standard/r2/sandboxes/HA1/batch_b55a9ca40300477e"
sandbox = out / "sandbox"
shutil.copytree(source, sandbox, symlinks=True)
shutil.copy2("docs/benchmarks/p1b_offline_20261025/ha1_r2_graph.json",
             sandbox / "mechanism_graph.json")
task = TaskSpec.model_validate_json(Path("ideapool/tasks/hard/HA1.json").read_text())
task.prompt.orchestration_mode = OrchestrationMode.STANDARD
result = BenchmarkRunner(out / "scorer").score_sandbox(task, sandbox)
(out / "score.json").write_text(json.dumps(asdict(result), ensure_ascii=False, indent=2))
print(result.final_score)
PY
```

本次实际使用的评分器提交见 `scorer_version.json`。复现所得综合分为 0.805；不同平台的解析器依赖与实际代码版本应一并记录。原始输入、日志和检查点仍通过 Drive 主包交付，不放入本目录。
