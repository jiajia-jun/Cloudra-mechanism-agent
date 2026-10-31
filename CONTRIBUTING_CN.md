# 参与 Cloudra 开发

[English](CONTRIBUTING.md)

感谢你考虑参与 Cloudra。Cloudra 是用于计算化学的研究软件，欢迎在issue区发表批评意见，我们会和您讨论问题。

使用反馈、复现问题、计算案例和文档改进同样欢迎。

## 开始之前

- 我们欢迎ai代码，但是请至少不要用oneshot式的生成，我们期待技术的交流。
- 我们推荐的与ai协作的模式是人机协同。您可以先看清楚接口，然后阻止ai产生过度工程或漏实现的问题。
- **大改动先开 issue。** 提前讨论方案，比代码写完后再发现分歧成本更低。

## 工程规则

完整规则见仓库 [AGENTS.md](AGENTS.md)。当前指南特别强调：

- 不用正则表达式验证结构化数据；使用 schema 和枚举，发现错误就明确报错。`re` 仅用于解析量子化学程序的原始文本输出。
- 不阻塞异步事件循环。同步数据库查询、`time.sleep`、`subprocess.run` 和阻塞网络请求，应交给 `asyncio.to_thread` 等方式处理。
- 不随意终止正在运行的量化作业。取消通过数据库标志传递，进程存活按文件锁判断。
- 修复 bug 时提供能够复现问题的单元测试，如有必要，希望能够提供集成测试。

## 开发检查

```bash
uv run python -m compileall -q cloudra tests   # 语法检查
uv run ruff check cloudra tests                # 代码规范
uv run pytest -q tests/test_dag_engine.py      # 检查本次修改涉及的模块
```

## 提交 Pull Request

- 一个 PR 聚焦一个逻辑改动。
- 行为变化时，在同一提交中更新相关文档和模块 README。
- 如果是大的重构，推荐将PR拆分为多个小PR，方便审阅。

## 报告问题

附上 Cloudra 版本或提交编号、执行命令和完整报错。计算问题还应提供输入几何及量子化学程序输出末尾的相关日志。直接提供程序输出，比转述报错更便于定位问题。

## 开发者来源声明（DCO）

每次提交都必须按 [Developer Certificate of Origin 1.1](https://developercertificate.org/) 签署。签署意味着你有权按项目许可证 AGPL-3.0-or-later 提交这份贡献，不代表转让版权；你仍保留自己工作的版权。

提交方式：

```bash
git commit -s -m "fix: correct TS optimizer convergence check"
```

命令会在提交说明中追加：

```text
Signed-off-by: Your Name <your.email@example.com>
```

姓名和邮箱必须真实，并与提交作者一致。为缺少签署的提交补充声明：

```bash
git commit --amend -s --no-edit     # 最近一次提交
git rebase --signoff HEAD~n          # 最近 n 次提交
```

没有有效签署的提交不会合并。
