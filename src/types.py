from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any


class LoopMode(str, Enum):
    HEARTBEAT = "heartbeat"
    NORMAL = "normal"
    SOULBEAT = "soulbeat"


@dataclass(slots=True)
class ToolCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class TimelineEvent:
    type: str
    text: str


@dataclass(slots=True)
class DistillResult:
    facts: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)
    active: list[str] = field(default_factory=list)
    discard: list[str] = field(default_factory=list)


@dataclass(slots=True)
class TimelineEntry:
    id: int
    ts: datetime
    mode: LoopMode
    text: str
    image_ref: str | None = None
    event_type: str | None = None
    tool_results: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ParsedModelOutput:
    idle: bool = False
    react: bool = False
    reply: str = ""
    event: TimelineEvent | None = None
    distill: DistillResult | None = None
    tool_calls: list[ToolCall] = field(default_factory=list)

