from __future__ import annotations

from datetime import datetime
from pathlib import Path

from .config_loader import MemoryConfig


class SessionMemory:
    def __init__(self, config: MemoryConfig) -> None:
        self.session_dir = Path(config.session_dir)
        self.user_facts_file = Path(config.user_facts_file)
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.user_facts_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.user_facts_file.exists():
            self.user_facts_file.write_text("# User Facts\n", encoding="utf-8")

    def append_events(self, events: list[str], when: datetime | None = None) -> Path:
        when = when or datetime.now()
        out_file = self.session_dir / f"{when:%Y-%m-%d}.md"
        if not out_file.exists():
            out_file.write_text(f"# Session {when:%Y-%m-%d}\n\n", encoding="utf-8")
        if events:
            lines = "\n".join(f"- [{when:%H:%M:%S}] {event}" for event in events)
            with out_file.open("a", encoding="utf-8") as fh:
                fh.write(lines + "\n")
        return out_file

    def upsert_user_facts(self, facts: list[str]) -> None:
        if not facts:
            return
        existing = self.user_facts_file.read_text(encoding="utf-8")
        with self.user_facts_file.open("a", encoding="utf-8") as fh:
            for fact in facts:
                marker = f"- {fact}"
                if marker not in existing:
                    fh.write(marker + "\n")

    def load_recent_session_summary(self) -> str:
        files = sorted(self.session_dir.glob("*.md"))
        if not files:
            return ""
        latest = files[-1]
        return latest.read_text(encoding="utf-8")[-1200:]

