"""HTTP 控制面（FastAPI v2）包。

由原单文件 ``api_v2.py`` 拆分而来，公开面不变：
``create_v2_app`` / ``create_default_v2_app`` 的导入路径与签名保持原样，
uvicorn factory 字符串 ``cloudra.services.api_v2:create_default_v2_app``
照常解析。路由按域分组在 ``routers/`` 子包，共享依赖经 ``ApiContext``
显式注入。
"""

from .app import create_default_v2_app, create_v2_app
from .context import ApiContext
from .models import (
    AgentSpawn,
    ApprovalDecision,
    CancelPost,
    CommandResponse,
    CompactRequest,
    ContextInjectRequest,
    DagMutationRequest,
    DagReplanRequest,
    GlobalConfigFieldPatch,
    GlobalConfigPatch,
    GoalSetRequest,
    InteractionResponse,
    MessagePost,
    ProjectCreate,
    ProjectPatch,
    RestartPost,
    RolePatch,
    _command_payload,
)
from .sse import _sse, _sse_replay

__all__ = [
    "AgentSpawn",
    "ApiContext",
    "ApprovalDecision",
    "CancelPost",
    "CommandResponse",
    "CompactRequest",
    "ContextInjectRequest",
    "DagMutationRequest",
    "DagReplanRequest",
    "GlobalConfigFieldPatch",
    "GlobalConfigPatch",
    "GoalSetRequest",
    "InteractionResponse",
    "MessagePost",
    "ProjectCreate",
    "ProjectPatch",
    "RestartPost",
    "RolePatch",
    "_command_payload",
    "_sse",
    "_sse_replay",
    "create_default_v2_app",
    "create_v2_app",
]
