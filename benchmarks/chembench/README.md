# Cloudra × ChemBench

本目录提供 [LamaLab ChemBench](https://github.com/lamalab-org/chembench) 与 Cloudra 的轻量集成，用于自动评估 Cloudra 配置的大模型在化学任务上的表现。

与直接调用 API 的轻量评测不同，本集成使用 **Cloudra 完整 Agent 管道**（Coordinator → ReAct → Tool → 最终答案）运行每道题目，更贴近真实化学研究场景。

## 前置准备

### 1. 安装依赖

```bash
cd benchmarks/chembench
pip install -r requirements.txt
```

### 2. 下载 ChemBench 数据集

```bash
git clone --depth=1 https://github.com/lamalab-org/chembench.git benchmarks/data/chembench-repo
```

### 3. 配置 Cloudra

确保 `.env` 或 `~/.config/cloudra/config.yaml` 中已正确配置 coordinator 的模型、URL 和 Key。

## 快速开始

### 使用本地数据集（推荐）

```bash
CLOUDRA_YOLO_MODE=true python -m benchmarks.chembench.run --limit 10
```

### 指定本地数据目录

```bash
CLOUDRA_YOLO_MODE=true python -m benchmarks.chembench.run \
    --data-dir benchmarks/data/chembench-repo/data
```

### 只跑有机化学子集

```bash
CLOUDRA_YOLO_MODE=true python -m benchmarks.chembench.run \
    --subset organic-chemistry \
    --run-id paper_v1
```

### 并发评测

```bash
CLOUDRA_YOLO_MODE=true python -m benchmarks.chembench.run \
    --concurrency 3 \
    --timeout 300
```

### 从 HuggingFace 加载数据

```bash
CLOUDRA_YOLO_MODE=true python -m benchmarks.chembench.run \
    --data-dir hf \
    --limit 10
```

> **注意**：`CLOUDRA_YOLO_MODE=true` 是必需的，用于跳过交互式审批，避免批量评测时进程阻塞。

## 命令行参数

| 参数 | 缩写 | 说明 | 默认值 |
|---|---|---|---|
| `--data-dir` | `-d` | ChemBench 本地数据目录（含按 topic 分组的 JSON 文件） | `benchmarks/data/chembench-repo/data` |
| `--limit` | `-n` | 只评测前 N 题（用于快速测试） | 全部 |
| `--subset` | `-s` | 只评测含指定关键词的题目，可重复指定多个 | 全部 |
| `--timeout` | `-t` | 每题最大等待时间（秒） | 300 |
| `--concurrency` | `-c` | 并发数（>1 时多题同时跑，建议 ≤ 4） | 1 |
| `--run-id` | | 自定义 run_id（默认自动生成） | `run_<uuid>` |
| `--quiet` | `-q` | 静默模式，不打印逐题进度 | False |

## 输出文件

评测结果写入 `data_dir/benchmarks/chembench/<run_id>/` 目录：

```
benchmarks/chembench/<run_id>/
├── summary.json          # 总体统计（正确率、MC 正确率、MAE 等）
├── questions/
│   ├── <uuid>.json       # 每题详情（含 conversation_id，可通过 API 查询）
│   └── ...
└── by_keyword/
    ├── organic-chemistry.json
    └── ...               # 按关键词分类的统计
```

每题的 JSON 包含指向 Cloudra conversation 的 `conversation_id`，可通过 `/conversations/{id}` API 复现任意一题的完整推理过程。

## 注意事项

- **YOLO 模式**：必须设置 `CLOUDRA_YOLO_MODE=true`，否则批量评测时 `approval_handler` 会通过 CLI `input()` 等待人工审批，导致进程阻塞。
- **数据集下载**：首次运行需联网下载 ChemBench 数据集（通过 git clone 或 HuggingFace）。
- **并发建议**：默认 `concurrency=1`（顺序执行）保证结果可复现；并发 ≤ 4 时 WAL 模式可支撑。
- **超时处理**：每题有独立超时（默认 300s），超时视为无效答案而非崩溃。
- **限流重试**：遇到 API 429 限流会自动指数退避重试（最多 8 次）。

## 引用

如果使用了 ChemBench，请引用原作者的工作：

```bibtex
@article{mirza2024large,
  title={Are large language models superhuman chemists?},
  author={Adrian Mirza and others},
  year={2024},
  journal={arXiv preprint arXiv:2404.01475}
}
```
