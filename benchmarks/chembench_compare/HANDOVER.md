# ChemBench CLI-vs-CLI 对比实验交接文档

> 状态：等待充值 / 切换可用模型后重启全量实验
> 最后更新：2026-07-05

---

## 1. 实验目标

在相同 ChemBench 题目上横向对比：

- **Baseline**：OpenCode CLI (`opencode run`)
- **Treatment**：Cloudra CLI (`cloudra run --new --yolo`)

两者均通过 CLI 直接调用并捕获输出，避免 mock。

---

## 2. 代码与脚本位置

| 项目 | 路径 |
|------|------|
| 对比脚本 | `/home/yyy2333/Cloudra/program/CLOUDRA/benchmarks/chembench_compare/scripts/run_comparison.sh` |
| 入口命令 | `chembench-compare`（已加入 PATH） |
| 数据目录 | `/home/yyy2333/Cloudra/program/CLOUDRA/benchmarks/data/chembench-repo/data` |
| 结果根目录 | `~/.local/share/cloudra/benchmarks/chembench-compare/` |

---

## 3. 已完成的工作

### 3.1 Pilot（10 题）

- 命令：`bash run_comparison.sh --limit 10 --run-id pilot_20260705_174659`
- 结果目录：`~/.local/share/cloudra/benchmarks/chembench-compare/logs/20260705_174659/`
- 结果：OpenCode 80.0% vs Cloudra 70.0%（样本极小，无统计意义）

### 3.2 全量尝试（失败）

- 命令：`bash run_comparison.sh --run-id full_20260705 --limit 2785`
- 失败原因：**OpenCode 账户余额不足**
  - 前约 102 题正常返回答案
  - 第 103 题之后全部返回 `answer=None`
  - 直接调用 opencode CLI 报错：`Error: Insufficient account balance`
- 已清理该次失败数据

---

## 4. 如何重启实验

### 4.1 充值 / 换模型

1. 给 OpenCode 账户充值，或
2. 使用其他有额度的 opencode 模型：
   ```bash
   bash run_comparison.sh --run-id full_YYYYMMDD --limit 2785 --opencode-model <model-name>
   ```

### 4.2 常用命令

```bash
# 10 题 pilot
bash /home/yyy2333/Cloudra/program/CLOUDRA/benchmarks/chembench_compare/scripts/run_comparison.sh --limit 10

# 100 题快速验证
bash /home/yyy2333/Cloudra/program/CLOUDRA/benchmarks/chembench_compare/scripts/run_comparison.sh --limit 100 --run-id quick_YYYYMMDD

# 全量 2785 题
bash /home/yyy2333/Cloudra/program/CLOUDRA/benchmarks/chembench_compare/scripts/run_comparison.sh --limit 2785 --run-id full_YYYYMMDD
```

### 4.3 查看结果

```bash
# 查看最新报告
ls -t ~/.local/share/cloudra/benchmarks/chembench-compare/logs | head -1
# 替换 <latest>
cat ~/.local/share/cloudra/benchmarks/chembench-compare/logs/<latest>/comparison/comparison.md
```

---

## 5. 已知问题

| 问题 | 说明 |
|------|------|
| 余额不足 | OpenCode 额度耗尽，全量实验无法继续 |
| 答案提取 | Cloudra 偶有 `...` 输出，可能是答案解析未命中 [ANSWER] 标记 |
| 速度 | 每题启动一次 CLI，全量预计数小时，建议夜间跑 |

---

## 6. 联系与下一步

- 充值/换模型后，重新跑全量
- 若换模型，请同步更新 `--opencode-model` 参数
- 建议先跑 `--limit 100` 确认新模型可用，再跑 2785
