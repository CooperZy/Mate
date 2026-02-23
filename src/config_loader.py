from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, Field


class BreathingConfig(BaseModel):
    heartbeat_interval: float = 0.4
    heartbeat_max_tokens: int = 50
    normal_interval: float = 1.5
    soulbeat_interval: float = 30.0
    soulbeat_max_tokens: int = 1024
    soulbeat_timeline_threshold: int = 20


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
    data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    return AppConfig.model_validate(data)

