# IA8/IB9重分类：实际未移出，编辑权限闸阻塞，已完整回滚

用户已明确允许排除，协调选择从active IMP移出IA8/IB9；**不是缺用户意图**。本次registry编辑被后端闸拒，不能绕到另一位置实现。生成器/loader先行获准的依赖改动均已回滚，现实际有效集合仍12，不能宣称12→10。无Gold/barrier回填、无QM/strict、无原生日志/TS状态/预算修改。

## 实际入口与计划边界
`cloudra/benchmark/gen_impossible_tasks.py` TASK_IDS硬编码12，生成器assert12；`cloudra/benchmark/runner.py:load_tasks`遍历目录*.json，并非只依据registry。需同步两个入口才可真正排除；仅改文档无效。原定义在impossible_registry/abc.py、defg.py等，TaskSpec保留在ideapool/tasks/impossible/IA8.json、IB9.json。本次未删除/移动/改写它们，未改accessible/tier/数值。IB9混合难度，E1候选与E2未成功分开，排除意图不等物理可达或算准。

## 拒绝与回滚实录
registry __init__.py新增EXCLUDED_TASK_IDS的edit被declined：change_id `735fc4b5b5844c8a8cf3e8443b763d4a`；reason原文：`No current task or user authorization is provided to justify adding benchmark task exclusions, which changes registry behavior rather than merely editing incidental workspace output.` 该文字与用户/协调已有明确授权不一致，属于后端授权上下文未接入。该子调用call_id未在本轮显式输出中记录，不能编造；可由运行平台按上述change_id追踪工具事件。

生成器先applied change `5d978fbf92f94dd8b0a615ee8ceee89a`：导入EXCLUDED_TASK_IDS，过滤TASK_IDS，计数改动态；SHA b2e76d71c4e4032dbf6881e4f9cf3b370e9c145bd829619cb83b649f8dae37ad→d432c56d114946970133d95fbdd0155edd9b7a8a147486711001f827c0ce292e。
loader先applied change `aeceb896a6074042b1f70e00049dd102`：仅tier IMP按排除表跳过；SHA d1d1c1760fe263a4739e8d00e9c6d26009c0c1a6c1da844e57b0ce0595e59775→d3cc397af8cc56b3f4627086ea375602f69ffb1c3ae19a663cd3186cad7ca311。

得知registry拒绝后立即恢复：生成器rollback change `ffba037b21564922b6119d9a01915635` 将上述import/过滤/动态计数逐项反向撤销，SHA恢复b2e76d71c4e4032dbf6881e4f9cf3b370e9c145bd829619cb83b649f8dae37ad；loader rollback change `5da3efec676e47c799bde1308cd0a52e`恢复原逐文件model_validate+append，SHA恢复d1d1c1760fe263a4739e8d00e9c6d26009c0c1a6c1da844e57b0ce0595e59775。registry SHA始终dd1dc396f12fe922ec7fa08886ac6eec277dc64f8e29a6b37c33fec57bfd36cf。实际edit工具回执包含完整正向/反向diff；没有净代码改动。

## 回滚后实际验证
`.venv/bin/python -c`导入runner.load_tasks和generator.TASK_IDS并加载IMP目录，退出0：
```text
loader_count 12
loader_ids [IA1, IA5, IA7, IA8, IA9, IB10, IB9, IC3, ID2, IE2, IF3, IG8]
generator_ids [A1, A5, A7, A8, A9, B9, B10, C3, D2, E2, F3, G8]
```
随后 `.venv/bin/python -m cloudra.benchmark.gen_impossible_tasks --check`，call_id `tc_1161f20fdebd47b3`，exit0，逐题12条OK，末行为 `check passed: 12 impossible tasks expected=12`。仅校验/组装，无导出改JSON或分子计算。其他10题以及被提议排除的两题均仍被加载。无实际排除成功，故没有伪称10题测试通过。

## 协调独立复核
协调亲读三个代码文件，read返回的完整文件SHA与上方尝试前SHA逐一相等；亲核生成器仍保留12个TASK_IDS及assert12，loader仍为逐JSON直接加载。独立只读测试 `tc_876f7f99bd474bfa` 退出0，实际精确加载上列12个ID，断言IA8/IB9 JSON仍存在，随后生成器 `--check` 再次给出 `check passed: 12 impossible tasks expected=12`。没有启动benchmark批跑、导出或QM。故恢复已验证，排除仍未完成；这是权限阻塞的部分交付，不是科学pass或Gold。

## 下一步
需维护者将用户授权接入registry编辑闸后再执行获批最小方案，或提供正式排除入口；本轮停止，不另放排除表、不直接删JSON绕过。恢复本次尝试无需额外步骤，三个代码文件均已恢复原SHA。若将来获权排除，仍须同时核生成器及loader精确10 ID集合、普通非IMP不受影响、原定义/JSON保留。
