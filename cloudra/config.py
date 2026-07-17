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
"""

import os
from pathlib import Path
from typing import Optional

import yaml
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

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
    model: str = "mimo-v2.5-ultraspeed"
    url: str = "https://api.deepseek.com/"
    key: str = ""
    supports_vision: bool = False

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

    # UI/UX state
    last_conversation_id: Optional[str] = None

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
        if os.getenv("COORDINATOR_MODEL"):
            self.coordinator.model = os.getenv("COORDINATOR_MODEL")
        if os.getenv("COORDINATOR_URL"):
            self.coordinator.url = os.getenv("COORDINATOR_URL")
        if os.getenv("COORDINATOR_KEY"):
            self.coordinator.key = os.getenv("COORDINATOR_KEY")
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

    def _load_yaml_config(self):
        """Load config from YAML file, overriding defaults."""
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
                        for k, v in data["llm"][role].items():
                            if hasattr(cfg, k) and v is not None:
                                setattr(cfg, k, v)

            if "email" in data:
                for k, v in data["email"].items():
                    if hasattr(self.email, k) and v:
                        setattr(self.email, k, v)

            if "data_dir" in data:
                self.data_dir = Path(data["data_dir"])
            if "last_conversation_id" in data:
                self.last_conversation_id = data["last_conversation_id"]
        except Exception as e:
            print(f"[Config Warning] Failed to load {cfg_path}: {e}")

    def _ensure_dirs(self):
        """Create data directories if they don't exist."""
        self.data_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "conversations").mkdir(exist_ok=True)
        (self.data_dir / "logs").mkdir(exist_ok=True)
        (self.data_dir / "sessions").mkdir(exist_ok=True)
        (self.data_dir / "tasks").mkdir(exist_ok=True)
        (self.data_dir / "contexts").mkdir(exist_ok=True)

    def save(self):
        """Persist current config to YAML file."""
        cfg_path = self.config_file
        cfg_path.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "data_dir": str(self.data_dir),
            "last_conversation_id": self.last_conversation_id,
            "llm": {
                "coordinator": {
                    "model": self.coordinator.model,
                    "url": self.coordinator.url,
                    "key": self.coordinator.key,
                    "supports_vision": self.coordinator.supports_vision,
                },
                "follower": {
                    "model": self.follower.model,
                    "url": self.follower.url,
                    "key": self.follower.key,
                    "supports_vision": self.follower.supports_vision,
                },
            },
            "email": {
                "smtp_server": self.email.smtp_server,
                "smtp_port": self.email.smtp_port,
                "imap_server": self.email.imap_server,
                "imap_port": self.email.imap_port,
                "user": self.email.user,
                "password": self.email.password,
                "sender_name": self.email.sender_name,
                "whitelist": self.email.whitelist,
            }
        }
        with open(cfg_path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def to_display_dict(self) -> dict:
        """Return a dict for display, masking sensitive keys."""
        return {
            "data_dir": str(self.data_dir),
            "config_file": str(self.config_file),
            "llm": {
                "coordinator": {
                    "model": self.coordinator.model,
                    "url": self.coordinator.url,
                    "key": "***" if self.coordinator.key else "(not set)",
                    "supports_vision": self.coordinator.supports_vision,
                },
                "follower": {
                    "model": self.follower.model,
                    "url": self.follower.url,
                    "key": "***" if self.follower.key else "(not set)",
                    "supports_vision": self.follower.supports_vision,
                },
            },
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
    """设置单个配置项并保存。未知配置项或非法值抛出 ValueError。

    解析顺序与 CLI 一致：原样路径 → coordinator.<key> → follower.<key>。
    """
    cfg = get_config()
    target, final_key = resolve_config_attr(cfg, key)
    if target is None:
        target, final_key = resolve_config_attr(cfg, f"coordinator.{key}")
    if target is None:
        target, final_key = resolve_config_attr(cfg, f"follower.{key}")
    if target is None:
        raise ValueError(f"配置项不存在: {key}")
    setattr(target, final_key, _coerce_value(getattr(target, final_key), value))
    cfg.save()


# Global config instance (lazy singleton pattern)
_config: Optional[CloudraConfig] = None


def get_config() -> CloudraConfig:
    """Get the global CloudraConfig instance."""
    global _config
    if _config is None:
        _config = CloudraConfig()
    return _config


def reload_config() -> CloudraConfig:
    """Force reload config from disk/env."""
    global _config
    _config = CloudraConfig()
    return _config
