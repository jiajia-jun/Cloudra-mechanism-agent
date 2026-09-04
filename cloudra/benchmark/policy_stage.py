"""`MethodPolicyStage` 已上移到 `cloudra.runtime_v2.policies.method_policy`
（GH #25：live pipeline 经 `default_stages(core)` 挂同一个 stage，按项目
settings 的 method_policy 拦截）。本模块仅做转引，保持 benchmark 侧既有
导入路径不变。
"""

from cloudra.runtime_v2.policies.method_policy import MethodPolicyStage  # noqa: F401
