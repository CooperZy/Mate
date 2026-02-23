from __future__ import annotations

from dataclasses import asdict
from datetime import datetime

from .config_loader import TimelineConfig
from .types import DistillResult, LoopMode, TimelineEntry


class TimelineManager:
    def __init__(self, config: TimelineConfig, distill_threshold: int) -> None:
        self.config = config
        self.distill_threshold = distill_threshold
        self._entries: list[TimelineEntry] = []
        self._next_id = 1
        self.summary = ""

    def add_entry(
        self,
        mode: LoopMode,
        text: str,
        image_ref: str | None = None,
        event_type: str | None = None,
        tool_results: list[dict] | None = None,
    ) -> TimelineEntry:
        entry = TimelineEntry(
            id=self._next_id,
            ts=datetime.now(),
            mode=mode,
            text=text,
            image_ref=image_ref,
            event_type=event_type,
            tool_results=tool_results or [],
        )
        self._next_id += 1
        self._entries.append(entry)
        if len(self._entries) > self.config.max_entries:
            self._entries = self._entries[-self.config.max_entries :]
        return entry

    def should_distill(self, elapsed_sec: float, has_long_running_query: bool = False) -> bool:
        enough_entries = len(self._entries) >= self.distill_threshold
        return (enough_entries and elapsed_sec >= 0) or has_long_running_query

    def entries(self) -> list[TimelineEntry]:
        return list(self._entries)

    def entries_as_dict(self) -> list[dict]:
        return [asdict(e) for e in self._entries]

    def apply_distill(self, distill: DistillResult) -> None:
        if distill.events:
            self.summary = (self.summary + "\n" + "\n".join(distill.events)).strip()
        if len(self._entries) > self.config.keep_after_distill:
            self._entries = self._entries[-self.config.keep_after_distill :]
        for active in distill.active:
            self.add_entry(mode=LoopMode.SOULBEAT, text=f"active:{active}", event_type="active")
