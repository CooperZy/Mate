from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

try:
    import yaml
except Exception:  # pragma: no cover - optional dependency fallback
    yaml = None  # type: ignore[assignment]

try:
    from pydantic import BaseModel, Field
except Exception:  # pragma: no cover - optional dependency fallback

    class _FieldDef:
        def __init__(self, default_factory):
            self.default_factory = default_factory

    def Field(default_factory):  # type: ignore[misc]
        return _FieldDef(default_factory)

    class BaseModel:
        def __init__(self, **kwargs: Any) -> None:
            annotations = getattr(self.__class__, "__annotations__", {})
            for name in annotations:
                if name in kwargs:
                    value = kwargs[name]
                else:
                    raw = getattr(self.__class__, name, None)
                    value = raw.default_factory() if isinstance(raw, _FieldDef) else raw
                setattr(self, name, value)

        @classmethod
        def model_validate(cls, data: dict[str, Any] | None):
            payload = data or {}
            kwargs: dict[str, Any] = {}
            for name in getattr(cls, "__annotations__", {}):
                raw = getattr(cls, name, None)
                if name in payload:
                    if isinstance(raw, _FieldDef):
                        nested = raw.default_factory()
                        nested_type = nested.__class__
                        if hasattr(nested_type, "model_validate"):
                            kwargs[name] = nested_type.model_validate(payload[name] or {})
                        else:
                            kwargs[name] = payload[name]
                    else:
                        kwargs[name] = payload[name]
                    continue
                if isinstance(raw, _FieldDef):
                    nested = raw.default_factory()
                    nested_type = nested.__class__
                    if hasattr(nested_type, "model_validate"):
                        kwargs[name] = nested_type.model_validate(payload.get(name) or {})
                    else:
                        kwargs[name] = nested
            return cls(**kwargs)


class BreathingConfig(BaseModel):
    heartbeat_interval: float = 0.4
    heartbeat_max_tokens: int = 50
    normal_interval: float = 1.5
    soulbeat_interval: float = 30.0
    soulbeat_max_tokens: int = 1024
    soulbeat_timeline_threshold: int = 20
    observation_mode: Literal["visual", "text_only", "off"] = "visual"
    heartbeat_only: bool = False


class TimelineConfig(BaseModel):
    max_entries: int = 24
    keep_after_distill: int = 8
    max_summary_tokens: int = 1000


class IdentityConfig(BaseModel):
    directory: str = "identity"
    hot_reload: bool = True


class MemoryConfig(BaseModel):
    session_dir: str = "memory/sessions"
    user_facts_file: str = "memory/user_facts.md"
    session_retention_days: int = 30


class ModelConfig(BaseModel):
    base_url: str = "http://localhost:8000/v1"
    model: str = "Qwen/Qwen2.5-VL-72B"
    temperature: float = 0.7
    max_tokens: int = 2048
    timeout_sec: float = 30.0
    retries: int = 1
    api_key: str = "EMPTY"


class AppConfig(BaseModel):
    breathing: BreathingConfig = Field(default_factory=BreathingConfig)
    timeline: TimelineConfig = Field(default_factory=TimelineConfig)
    identity: IdentityConfig = Field(default_factory=IdentityConfig)
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
    model: ModelConfig = Field(default_factory=ModelConfig)


def load_config(path: str | Path = "config/config.yaml") -> AppConfig:
    config_path = Path(path)
    if not config_path.exists():
        return AppConfig()

    if yaml is None:
        return AppConfig()

    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data)
