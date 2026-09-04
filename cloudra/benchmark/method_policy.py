"""方法白名单判定纯函数已上移到 `cloudra.runtime_v2.method_policy`（GH #25：
live pipeline 的 MethodPolicyStage 同样需要这套判定，而 runtime_v2 不能
反向依赖 benchmark）。本模块仅做转引，保持 benchmark 侧既有导入路径不变。
"""

from cloudra.runtime_v2.method_policy import (  # noqa: F401
    MethodVerdict,
    check_input_content,
    check_input_files,
    check_method,
    extract_embedded_inputs,
    intercept,
    referenced_input_paths,
)
from cloudra.runtime_v2.schemas import MethodPolicy  # noqa: F401
