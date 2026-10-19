# 独立 IRC 端点交接证据

交付说明：[归档报告](../../archive/2026-10-19-irc-endpoint-handoff.md)。

## E1 原件重放

需要先恢复 issue #210 作者的外部证据包，保持目录中的原始 SHA256SUMS。不要把原始日志替换成合成测试材料。

```bash
.venv/bin/python docs/evidence/qm_consistency_20261019/cloudra_e1_native_replay.py /absolute/path/to/evidence/e1-irc-20261019
.venv/bin/python docs/evidence/irc_handoff_20261019/e1_direct_recovery.py /absolute/path/to/evidence/e1-irc-20261019/calc
```

第一项重建实际 DAG 提交，原件只读，输出与临时配置在 `/tmp`；不恢复作者原数据库的审批状态。第二项核对自动导出与验收的规范外帧，并准备重算输入，不提交 QM。实际输出：[恢复探针](outputs/e1_direct_recovery.json)。

## 回归范围

- `test_irc_endpoint_artifacts`：原生 Gaussian/ORCA、双端精度、只读、幂等、篡改、单侧、异常终止与写入失败。
- `test_compute_execution_evidence`、`test_compute_transport_paths`：本地/Slurm 冻结、旧收据、远端 native/stdout 回收。
- `test_query_compute_job`、`test_runtime_v2_compute_notify`：同一路径经真实查询、邮箱通知、Artifact 归档交付，读取不阻塞事件循环。
- `test_gaussian_irc_evidence`、`test_irc_lineage_wrappers`、`test_irc_endpoint_optimization`：真实 IRC + 明确标注的合成 Opt/Freq 解析材料；有效链通过，错起点仍拒绝并提供具体恢复材料。
- `test_dag_file_science_cache`：派生文件损坏撤下恢复路径，科学判定仍由原生计算证据决定。

原生解析与源归档始终是验收真值。导出的 XYZ 是续算输入，不是新计算结果；本机没有 Gaussian/ORCA，本次未运行新 QM 或完整 easy 任务。完整源代码见 [source-chain.md](source-chain.md)。
