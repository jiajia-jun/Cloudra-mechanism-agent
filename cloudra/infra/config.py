"""
Cloudra configuration management.

Supports layered config:
  1. CLI arguments (highest priority)
  2. Config file (~/.config/cloudra/config.yaml)
  3. Environment variables (CLOUDRA_* and legacy COORDINATOR_* / FOLLOWER_*)
  4. .env file in the current working directory
  5. Defaults (lowest priority)

Note: the config file takes precedence over environment variables and .env,
so values set via `cloudra config init` / `cloudra config set` are always
effective. Environment variables are still supported for backward compatibility
and CI/automation use cases, but the YAML config is the recommended source of
truth for local development.

写路径纪律：磁盘 YAML 是唯一事实源，进程内单例只是其缓存。所有写一律走
``mutate_config(fn)``——flock（config.yaml.lock）下读磁盘最新状态 → fn 修改
→ atomic_write_text 原子写回 → 单例从磁盘重载。多进程并发写不丢更新；
不存在任何"内存快照整文件重写"的路径。
"""

import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Optional

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from cloudra.persistence.fs_utils import atomic_write_text

logger = logging.getLogger(__name__)

# Try platformdirs, fallback to appdirs or manual
try:
    from platformdirs import user_config_dir, user_data_dir
except ImportError:
    def user_config_dir(app):
        return Path.home() / ".config" / app

    def user_data_dir(app):
        return Path.home() / ".local" / "share" / app


APP_NAME = "cloudra"
DEFAULT_CONFIG_PATH = Path(user_config_dir(APP_NAME)) / "config.yaml"
DEFAULT_DATA_DIR = Path(user_data_dir(APP_NAME))


class LLMConfig(BaseSettings):
    """LLM provider configuration for a single agent type."""
    # 供应商 ID：openrouter / opencode_go / deepseek / openai / gemini / dashscope /
    # siliconflow / moonshot / zhipu / ollama / custom 等，可自动补全或探测端点
    provider: str = ""
    model: str = "deepseek-4-pro"
    url: str = "https://api.deepseek.com/"
    key: str = ""
    supports_vision: bool = True
    # 模型原生网页搜索：off / auto / openai / openrouter / deepseek / gemini / custom。
    # 默认 auto：按 base_url+model 自动识别并启用服务商侧搜索；
    # off 时保持传统 web_search 工具调用。
    native_search: str = "auto"
    # 原生搜索注入参数（verbatim 写入 extra_body）。custom 与无原生搜索的服务商
    # （如中转站 DeepSeek）用它指定 {plugins/ web_search_options / tools} 等字段。
    native_search_params: dict = Field(default_factory=dict)
    # 模型真实上下文窗口（token 数）：上下文压缩阈值按 window // 2 计算。
    # 默认偏保守：宁可比服务商标称窗口略小、早一点压缩，也不让对话拖成
    # 脏上下文；按模型性质覆盖请改 config.yaml / `cloudra config set`。
    context_window: int = 200000
    # 单次 LLM 请求超时秒数（OpenAI SDK 与 requests shim 共用）
    timeout: int = 300
    # 思考强度（OpenAI 兼容 reasoning_effort）：取值集随 provider 而异
    # （minimal/low/medium/high 等），None = 不传该参数。空 per-agent
    # settings 经 legacy_default_settings 回落到本槽位。
    reasoning_effort: str | None = None

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class EmailConfig(BaseSettings):
    """SMTP/IMAP configuration for notifications and interaction."""
    smtp_server: str = "smtp.gmail.com"
    smtp_port: int = 465
    imap_server: str = "imap.gmail.com"
    imap_port: int = 993
    user: str = ""
    password: str = ""  # Should be an app password
    sender_name: str = "Cloudra Assistant"
    whitelist: list[str] = []
    poll_interval: int = 60  # seconds between IMAP inbox polls (listener)

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class FlowerConfig(BaseSettings):
    """FlowER mechanism-prediction external environment.

    总开关 enabled 默认关：置 true 前必须先用 scripts/setup_flower.sh 装好
    独立 conda env 并填好 repo_dir/env_python/checkpoint。开关关闭时
    mechanism_predict 工具对模型隐藏（wire 投影）且执行层硬失败。
    """
    enabled: bool = False
    repo_dir: str = ""
    env_python: str = ""
    checkpoint: str = ""

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class ComputeConfig(BaseSettings):
    """计算执行面开关。

    allow_local_calculator 默认关：关闭时只用项目内置 calculator.sh，忽略作业
    工作目录里的同名脚本——工作目录是 agent 可写区，本地优先通道会把 agent
    放置的任意脚本提升为计算执行入口。确需按任务目录定制时显式置 true。
    """
    allow_local_calculator: bool = False

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class MethodPolicyConfig(BaseSettings):
    """benchmark 方法白名单的内容源（唯一事实源；生成器从这里读）。

    拦截仍只在 benchmark 强制（普通项目 ProjectSettings.method_policy=None 不启用）。
    改这里之后必须重跑 gen_*_tasks.py 重新生成题集；regenerate-identically 守卫
    会核对题集与本配置的默认值一致（测试环境走默认值）。
    """
    # easy/normal/hard 档共用（组合条目把基组钉进许可）
    allowed_methods: list[str] = Field(default_factory=lambda: ["xtb", "b3lyp/def2svp"])
    # impossible 档保持 xtb-only
    allowed_methods_impossible: list[str] = Field(default_factory=lambda: ["xtb"])

    model_config = SettingsConfigDict(env_prefix="", extra="ignore")


class CloudraConfig(BaseSettings):
    """Global Cloudra configuration."""

    model_config = SettingsConfigDict(
        env_prefix="CLOUDRA_",
        env_nested_delimiter="__",
        extra="ignore",
        env_file=".env",
        env_file_encoding="utf-8",
    )

    # Paths
    data_dir: Path = Field(default_factory=lambda: Path(user_data_dir(APP_NAME)))
    config_file: Path = Field(default_factory=lambda: Path(user_config_dir(APP_NAME)) / "config.yaml")

    # LLM configs
    coordinator: LLMConfig = Field(default_factory=LLMConfig)
    follower: LLMConfig = Field(default_factory=LLMConfig)

    # Email config
    email: EmailConfig = Field(default_factory=EmailConfig)

    # FlowER 机理推断外部环境（默认关闭）
    flower: FlowerConfig = Field(default_factory=FlowerConfig)

    # benchmark 方法白名单内容源（生成器读取；拦截只在 benchmark 强制）
    method_policy: MethodPolicyConfig = Field(default_factory=MethodPolicyConfig)

    # 计算执行面开关（本地 calculator.sh 通道默认关闭）
    compute: ComputeConfig = Field(default_factory=ComputeConfig)

    # OpenAlex 文献检索。空则匿名调用（额度更低）；可设 CLOUDRA_OPENALEX_API_KEY / OPENALEX_API_KEY。
    openalex_api_key: str = ""
    # 礼貌池邮箱，写入 User-Agent 的 mailto；空则只用通用 UA。可设 CLOUDRA_OPENALEX_MAILTO / OPENALEX_MAILTO。
    openalex_mailto: str = ""

    # 通用插件（知识图书馆层、事件观察者等）：dotted path 列表，
    # "pkg.module:attr"，attr 为插件实例或无参工厂（带 name；hooks 可选：
    # search / on_event / setup）。应用启动时加载一次；失败只记日志不阻塞。
    plugins: list[str] = Field(default_factory=list)

    # 知识向量微服务（kg_vec）的解释器：指向装 torch/sentence-transformers 的
    # .venv-trans python；空串时 web_launcher 按仓库根 .venv-trans/bin/python
    # 自动探测。env CLOUDRA_KNOWLEDGE_VEC_PYTHON 可覆盖。
    knowledge_vec_python: str = ""

    @field_validator("data_dir", "config_file", mode="before")
    @classmethod
    def _coerce_path(cls, v):
        if isinstance(v, str):
            return Path(v)
        return v

    def model_post_init(self, __context):
        # Backward compatibility: read legacy .env vars
        self._load_legacy_env()
        # Load YAML config file if it exists
        self._load_yaml_config()
        # Ensure data dirs exist
        self._ensure_dirs()

    def _load_legacy_env(self):
        """Read COORDINATOR_* / FOLLOWER_* from environment or .env."""
        # These may have been loaded by pydantic-settings from .env already,
        # but we also check them directly to be safe.
        if os.getenv("COORDINATOR_PROVIDER"):
            self.coordinator.provider = os.getenv("COORDINATOR_PROVIDER")
        if os.getenv("COORDINATOR_MODEL"):
            self.coordinator.model = os.getenv("COORDINATOR_MODEL")
        if os.getenv("COORDINATOR_URL"):
            self.coordinator.url = os.getenv("COORDINATOR_URL")
        if os.getenv("COORDINATOR_KEY"):
            self.coordinator.key = os.getenv("COORDINATOR_KEY")
        if os.getenv("FOLLOWER_PROVIDER"):
            self.follower.provider = os.getenv("FOLLOWER_PROVIDER")
        if os.getenv("FOLLOWER_MODEL"):
            self.follower.model = os.getenv("FOLLOWER_MODEL")
        if os.getenv("FOLLOWER_URL"):
            self.follower.url = os.getenv("FOLLOWER_URL")
        if os.getenv("FOLLOWER_KEY"):
            self.follower.key = os.getenv("FOLLOWER_KEY")

        # Email legacy envs
        if os.getenv("SMTP_USER"):
            self.email.user = os.getenv("SMTP_USER")
        if os.getenv("SMTP_PASS"):
            self.email.password = os.getenv("SMTP_PASS")

        if not self.openalex_api_key and os.getenv("OPENALEX_API_KEY"):
            self.openalex_api_key = os.getenv("OPENALEX_API_KEY") or ""
        if not self.openalex_mailto and os.getenv("OPENALEX_MAILTO"):
            self.openalex_mailto = os.getenv("OPENALEX_MAILTO") or ""

    def _load_yaml_config(self):
        """Load config from YAML file, overriding in-memory values.

        磁盘 YAML 是唯一事实源：文件里出现的键原样生效（含空串/空列表，
        清空语义要能往返）；只有 None（手写 YAML 的"留空"）才跳过。
        """
        cfg_path = self.config_file
        if not cfg_path.exists():
            return
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            if "llm" in data:
                for role in ("coordinator", "follower"):
                    if role in data["llm"]:
                        cfg = getattr(self, role)
                        role_data = data["llm"][role]
                        if "provider" in role_data and role_data["provider"]:
                            from cloudra.infra.providers import apply_provider_preset
                            apply_provider_preset(cfg, str(role_data["provider"]))
                        for k, v in role_data.items():
                            if hasattr(cfg, k) and v is not None:
                                setattr(cfg, k, v)
                        if not cfg.provider and cfg.url:
                            from cloudra.infra.providers import detect_provider_from_url
                            detected = detect_provider_from_url(cfg.url)
                            if detected:
                                cfg.provider = detected.id

            if "email" in data:
                for k, v in data["email"].items():
                    if hasattr(self.email, k) and v is not None:
                        setattr(self.email, k, v)

            if "flower" in data:
                for k, v in data["flower"].items():
                    if hasattr(self.flower, k) and v is not None:
                        setattr(self.flower, k, v)

            if "method_policy" in data:
                for k, v in data["method_policy"].items():
                    if hasattr(self.method_policy, k) and v is not None:
                        setattr(self.method_policy, k, v)

            if "compute" in data:
                for k, v in data["compute"].items():
                    if hasattr(self.compute, k) and v is not None:
                        setattr(self.compute, k, v)

            if "data_dir" in data and data["data_dir"] is not None:
                self.data_dir = Path(data["data_dir"])
            if "openalex_api_key" in data and data["openalex_api_key"] is not None:
                self.openalex_api_key = str(data["openalex_api_key"])
            if "openalex_mailto" in data and data["openalex_mailto"] is not None:
                self.openalex_mailto = str(data["openalex_mailto"])
            if "plugins" in data and data["plugins"] is not None:
                self.plugins = [str(s) for s in data["plugins"]]
            if "knowledge_vec_python" in data and data["knowledge_vec_python"] is not None:
                self.knowledge_vec_python = str(data["knowledge_vec_python"])
        except Exception as e:
            logger.warning("Failed to load %s: %s", cfg_path, e)

    def _ensure_dirs(self):
        """Create data directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "conversations").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)
        (self.data_dir / "contexts").mkdir(exist_ok=True)

    def to_display_dict(self) -> dict:
        """Return a dict for display, masking sensitive keys."""
        def _slot_dict(role: LLMConfig) -> dict:
            from cloudra.infra.providers import detect_provider_from_url
            provider_id = role.provider
            if not provider_id and role.url:
                detected = detect_provider_from_url(role.url)
                provider_id = detected.id if detected else "custom"
            return {
                "provider": provider_id or "custom",
                "model": role.model,
                "url": role.url,
                "key": "***" if role.key else "(not set)",
                "supports_vision": role.supports_vision,
                "native_search": role.native_search,
                "native_search_params": role.native_search_params,
                "context_window": role.context_window,
                "timeout": role.timeout,
                "reasoning_effort": role.reasoning_effort,
            }

        return {
            "data_dir": str(self.data_dir),
            "config_file": str(self.config_file),
            "llm": {
                "coordinator": _slot_dict(self.coordinator),
                "follower": _slot_dict(self.follower),
            },
            "openalex_api_key": "***" if self.openalex_api_key else "(not set)",
            "openalex_mailto": self.openalex_mailto or "(not set)",
        }


def resolve_config_attr(cfg: CloudraConfig, key: str):
    """Resolve a dot-path like 'llm.coordinator.model' against a Pydantic model.

    Returns (target, final_key) or (None, None) when the path does not exist.
    """
    parts = key.split(".")
    target = cfg
    for part in parts[:-1]:
        if hasattr(target, part):
            target = getattr(target, part)
        else:
            return None, None
    final_key = parts[-1]
    if not hasattr(target, final_key):
        return None, None
    return target, final_key


def _coerce_value(current, value: str):
    """按配置项当前值的类型把字符串输入转为对应类型。"""
    if isinstance(current, bool):
        lowered = value.strip().lower()
        if lowered in ("1", "true", "yes", "on"):
            return True
        if lowered in ("0", "false", "no", "off"):
            return False
        raise ValueError(f"布尔配置项只接受 true/false/1/0/yes/no/on/off，收到: {value}")
    if isinstance(current, int):
        try:
            return int(value.strip())
        except ValueError:
            raise ValueError(f"整数配置项收到非法值: {value}") from None
    if isinstance(current, dict):
        import json
        try:
            parsed = json.loads(value.strip())
        except json.JSONDecodeError as exc:
            raise ValueError(f"字典配置项 JSON 解析失败: {exc}") from None
        if not isinstance(parsed, dict):
            raise ValueError("字典配置项需要 JSON 对象")
        return parsed
    if isinstance(current, list):
        stripped = value.strip()
        if stripped.startswith("["):
            import json
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"列表配置项 JSON 解析失败: {exc}") from None
            if not isinstance(parsed, list):
                raise ValueError("列表配置项需要 JSON 数组或逗号分隔字符串")
            return parsed
        return [item.strip() for item in stripped.split(",") if item.strip()]
    if isinstance(current, Path):
        return Path(value).expanduser()
    return value


def set_config_value(key: str, value: str) -> None:
    """设置单个配置项并原子落盘。未知配置项或非法值抛出 ValueError。

    解析顺序与 CLI 一致：原样路径 → coordinator.<key> → follower.<key>。
    """

    def _apply(work: CloudraConfig) -> None:
        target, final_key = resolve_config_attr(work, key)
        if target is None:
            target, final_key = resolve_config_attr(work, f"coordinator.{key}")
        if target is None:
            target, final_key = resolve_config_attr(work, f"follower.{key}")
        if target is None:
            raise ValueError(f"配置项不存在: {key}")
        if final_key == "provider" and isinstance(target, LLMConfig):
            from cloudra.infra.providers import apply_provider_preset, get_provider_preset
            preset = get_provider_preset(value)
            if preset and preset.id != "custom":
                apply_provider_preset(target, preset.id)
            else:
                target.provider = value
            return
        if final_key == "url" and isinstance(target, LLMConfig):
            from cloudra.infra.providers import detect_provider_from_url
            target.url = value
            detected = detect_provider_from_url(value)
            if detected:
                target.provider = detected.id
            return
        setattr(target, final_key, _coerce_value(getattr(target, final_key), value))

    mutate_config(_apply)


# Global config instance (lazy singleton pattern)
_config: Optional[CloudraConfig] = None


def get_config() -> CloudraConfig:
    """Get the global CloudraConfig instance."""
    global _config
    if _config is None:
        _config = CloudraConfig()
    return _config


def _model_to_yaml_data(cfg: CloudraConfig) -> dict:
    """从 model_dump 派生 YAML 文档，不维护手抄字段清单。

    唯一的结构映射：两个 LLM 槽位在磁盘上嵌套于 llm 键；其余顶层字段
    （email/openalex_*/plugins 及未来新增字段）随 model_dump 自动跟随。
    config_file 是进程内寻址信息，不落盘。
    """
    dump = cfg.model_dump(mode="json", exclude={"config_file"})
    data = {
        "data_dir": dump.pop("data_dir"),
        "llm": {
            "coordinator": dump.pop("coordinator"),
            "follower": dump.pop("follower"),
        },
    }
    data.update(dump)
    return data


def mutate_config(fn: Callable[[CloudraConfig], None]) -> CloudraConfig:
    """唯一配置写入口：flock 下读磁盘 → fn(工作副本) → 原子写回 → 单例从磁盘重载。

    fn 收到的工作副本 = 进程当前配置叠加磁盘 YAML 最新状态（磁盘优先），
    因此多进程并发的读-改-写不会互相抹键；flock（config.yaml 旁的
    config.yaml.lock）把临界区跨进程/线程串行化。fn 抛错时不写盘、
    不动单例。返回刷新后的全局单例。
    """
    from cloudra.infra.flocks import locked  # 惰性导入：flocks 依赖 POSIX fcntl

    cfg = get_config()
    cfg_path = Path(cfg.config_file)
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    with locked(str(cfg_path) + ".lock"):
        work = cfg.model_copy(deep=True)
        work._load_yaml_config()  # 磁盘覆盖内存：并发的最新写入不被旧快照抹掉
        fn(work)
        atomic_write_text(str(cfg_path), yaml.dump(
            _model_to_yaml_data(work),
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        ))
        # 单例回填为刚落盘的磁盘状态（就地更新，嵌套对象身份不变，
        # 持有 get_config() 引用的调用方立即可见）。
        cfg._load_yaml_config()
    return cfg


def add_plugin(spec: str) -> bool:
    """幂等把插件 spec（"pkg.module:attr"）加进 plugins；返回是否新增。"""
    added = False

    def _apply(work: CloudraConfig) -> None:
        nonlocal added
        if spec not in work.plugins:
            work.plugins = [*work.plugins, spec]
            added = True

    mutate_config(_apply)
    return added


def remove_plugin(spec: str) -> bool:
    """幂等从 plugins 移除插件 spec；返回是否移除。"""
    removed = False

    def _apply(work: CloudraConfig) -> None:
        nonlocal removed
        if spec in work.plugins:
            work.plugins = [s for s in work.plugins if s != spec]
            removed = True

    mutate_config(_apply)
    return removed


def _reset_for_tests() -> CloudraConfig:
    """测试专用：丢弃进程内单例并按当前环境重建。生产代码禁止调用。

    测试用 monkeypatch.setenv 改 CLOUDRA_* / legacy env 后调用它，
    让单例反映新环境。
    """
    global _config
    _config = CloudraConfig()
    return _config
