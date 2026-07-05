# ChemBench CLI-vs-CLI 对比评测：Cloudra vs OpenCode

本目录提供一套**统一、可复现**的 ChemBench 横向对比评测框架。
设计原则：**两边都通过各自的 CLI 直接调用，并捕获原始输出进行评分**。

- **Baseline**: `opencode run`（通用编程助手）
- **Treatment**: `cloudra run --new --yolo`（Cloudra 化学科研 Agent）

这样对比最公平：两者都是 CLI 工具，调用方式一致，只比较底层 agent
在化学问题上的回答质量。

## 架构

```
benchmarks/chembench_compare/
├── cli.py                  # 统一 CLI：run / compare
├── compare.py              # Baseline/Treatment 合并与报告
├── README.md
└── runners/
    ├── __init__.py         # namespace 注册
    ├── base.py             # BaseRunner（共享循环、评分、持久化）
    ├── opencode.py         # opencode run 调用
    └── cloudra_cli.py      # cloudra run --yolo 调用
```

共享组件：

```
benchmarks/chembench/
├── adapter.py              # question -> prompt
├── evaluator.py            # 答案提取与评分
├── report.py               # 结果持久化
└── utils.py                # get_field 等通用 helper
```

## 前置条件

1. ChemBench 数据已下载到 `benchmarks/data/chembench-repo/data`。
2. `opencode` CLI 与 `cloudra` CLI 都在 PATH 中。
3. Cloudra 配置正确（`.env` 或 `~/.config/cloudra/config.yaml`）。
4. 两边使用**同一模型**（OpenCode 默认复用 Cloudra coordinator 的模型名）。

## 命令概览

统一入口：`chembench-compare`

| 命令 | 作用 |
|------|------|
| `chembench-compare run --runner opencode ...` | 用 OpenCode CLI 跑 ChemBench |
| `chembench-compare run --runner cloudra-cli ...` | 用 Cloudra CLI 跑 ChemBench |
| `chembench-compare compare --baseline ... --treatment ...` | 合并两份结果生成报告 |

别名（向后兼容）：

- `chembench-opencode` → `chembench-compare run --runner opencode`
- `chembench-cloudra-cli` → `chembench-compare run --runner cloudra-cli`

## 快速开始

### 1. 跑 OpenCode 基线

```bash
chembench-compare run \
    --runner opencode \
    --limit 100 \
    --run-id opencode_v1
```

### 2. 跑 Cloudra

```bash
chembench-compare run \
    --runner cloudra-cli \
    --limit 100 \
    --run-id cloudra_cli_v1
```

### 3. 合并对比

```bash
chembench-compare compare \
    --baseline opencode_v1 \
    --baseline-mode opencode \
    --baseline-label OpenCode \
    --treatment cloudra_cli_v1 \
    --treatment-mode cloudra-cli \
    --treatment-label Cloudra
```

输出：

```
~/.local/share/cloudra/benchmarks/chembench-compare/reports/compare_YYYYMMDD_HHMMSS/
├── comparison.json
├── comparison.md
└── per_question.csv
```

## 输出目录结构

```
~/.local/share/cloudra/benchmarks/
├── chembench-compare/
│   ├── opencode/                  # OpenCode CLI 结果
│   │   └── opencode_v1/
│   ├── cloudra-cli/               # Cloudra CLI 结果
│   │   └── cloudra_cli_v1/
│   └── reports/                   # 合并报告
│       └── compare_YYYYMMDD_HHMMSS/
│           ├── comparison.json
│           ├── comparison.md
│           └── per_question.csv
```

## CLI 参数

### `chembench-compare run`

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `-r, --runner` | 后端 runner（必填） | — |
| `-d, --data-dir` | ChemBench 本地数据目录 | `benchmarks/data/chembench-repo/data` |
| `-n, --limit` | 只评测前 N 题 | 全部 |
| `-s, --subset` | 按关键词过滤，可重复 | 全部 |
| `-t, --timeout` | 每题超时（秒） | 300 |
| `--run-id` | 自定义 run_id | 自动生成 |
| `--opencode-model` | OpenCode 模型名 | Cloudra coordinator 模型 |
| `-q, --quiet` | 静默模式 | False |

### `chembench-compare compare`

| 参数 | 说明 |
|------|------|
| `-b, --baseline` | Baseline run_id 或目录路径 |
| `-t, --treatment` | Treatment run_id 或目录路径 |
| `--baseline-mode` | Baseline runner 类型 |
| `--treatment-mode` | Treatment runner 类型 |
| `--baseline-label` | 报告中 Baseline 显示名称 |
| `--treatment-label` | 报告中 Treatment 显示名称 |
| `-O, --output` | 报告输出目录 |

## 报告内容

`comparison.md` 包含：

- 总体正确率、MC 正确率、数值 MAE 均值
- 分 topic 正确率与 delta
- 双方都对 / 都错 / 仅 Treatment 对 / 仅 Baseline 对的题数
- Treatment 提升/退步的典型题目列表

`per_question.csv` 包含每道题的：uuid、name、topic、两侧答案、两侧是否正确、标签。

## 调用细节

两者都是直接调用 CLI，传入 prompt，捕获 stdout/stderr：

- OpenCode: `opencode [--model <model>] run <prompt>`
- Cloudra: `cloudra run --new --yolo <prompt>`

prompt 通过 `benchmarks.chembench.adapter.question_to_query()` 统一构造，
确保两边看到完全相同的题目描述和 `[ANSWER]...[/ANSWER]` 格式要求。

## 注意事项

1. **模型一致**：OpenCode 默认复用 Cloudra coordinator 的模型名；请确认两侧实际调用同一模型。
2. **CLI 开销**：`opencode run` 与 `cloudra run` 每次启动都有 CLI 初始化开销，
   单题 wall time 可以记录但不宜作为核心指标。
3. **非确定性**：大模型输出有随机性，建议固定 temperature=0 并多次运行取平均。

## 扩展

新增 CLI backend 只需：
1. 在 `runners/` 下创建文件，继承 `BaseRunner`。
2. 实现 `_invoke(prompt) -> str` 调用对应 CLI 并清理输出。
3. 在 `runners/__init__.py` 的 `NAMESPACE_MAP` 中注册 namespace。
4. 在 `cli.py` 的 `--runner` Choice 中加入新名称。
