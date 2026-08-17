# Cloudra documentation

这个目录放实现、部署和验证文档。项目定位、研究问题和方法贡献写在仓库根目录的 [`README.md`](../README.md) 和 [`README_CN.md`](../README_CN.md)，这里不重复。

## 使用与部署

| 文档 | 适用场景 | 当前状态 |
| --- | --- | --- |
| `cloudra` / `cloudra web` | 一键安装 npm 依赖、构建并启动 Electron/浏览器前端 | 当前推荐入口；Node.js >= 18 |
| [`deploy/node-registry.example.json`](../deploy/node-registry.example.json) | 多节点、工作区、local/Slurm scheduler 配置 | 配置示例；路径需按部署环境修改 |

## 架构与协议

| 文档 | 内容 | 当前状态 |
| --- | --- | --- |
| [`PHASE8_NODE_REGISTRY.md`](PHASE8_NODE_REGISTRY.md) | 多服务器 profile、节点/工作区路由、能力命名空间、worker lease、Slurm 恢复语义 | 当前实现说明；物理多节点 gateway 待后续验证 |
| [`DAG_ORCHESTRATION.md`](DAG_ORCHESTRATION.md) | DAG 引导编排：机理图 + 阶段契约 + CallReview 收件箱、三模式消融边界、分权与证据派生、Supervisor 触发 | 当前实现说明；按会话 opt-in |

那份架构计划还在开发环境的次要目录，不会随 Python 包一起发布。如果要放到公开仓库引用，先整理成仓库内的稳定文档，不要引用某台机器上的绝对路径。

## 验证

| 文档 | 内容 | 当前状态 |
| --- | --- | --- |

自动化测试在 `tests/`。目前还没有正式的 benchmark 报告、模型对比表或可引用的科研性能结论。本仓库不再包含 `benchmarks/` 目录；历史评测素材已删除。

## 文档维护约定

- README 只保留研究动机、方法、验证边界和最短上手路径。
- 操作步骤放在使用/运维文档，协议字段和状态机放在架构文档。
- “已实现”“自动化测试通过”“真实环境验收通过”要分开表述。
- 新增 benchmark 数字时，同时记录 commit、数据版本、模型、prompt、工具 revision、运行环境、随机性设置和失败样本，别只丢一张汇总表。
- 版本或命令变化后，同步更新中英文 README 和本索引。
