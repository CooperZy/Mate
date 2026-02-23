from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from .config_loader import MemoryConfig


class SessionMemory:
    def __init__(self, config: MemoryConfig) -> None:
        self.session_dir = Path(config.session_dir)
        self.user_facts_file = Path(config.user_facts_file)
        self.session_retention_days = config.session_retention_days
        self.session_dir.mkdir(parents=True, exist_ok=True)
        self.user_facts_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.user_facts_file.exists():
            self.user_facts_file.write_text("# User Facts\n", encoding="utf-8")
        self._cleanup_old_sessions()

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

        existing_lines = self.user_facts_file.read_text(encoding="utf-8").splitlines()
        seen = {line[2:].strip().lower() for line in existing_lines if line.startswith("- ")}

        new_lines: list[str] = []
        for fact in facts:
            normalized = fact.strip().lower()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            new_lines.append(f"- {fact.strip()}")

        if new_lines:
            with self.user_facts_file.open("a", encoding="utf-8") as fh:
                fh.write("\n".join(new_lines) + "\n")

    def load_recent_session_summary(self) -> str:
        files = sorted(self.session_dir.glob("*.md"))
        if not files:
            return ""
        latest = files[-1]
        return latest.read_text(encoding="utf-8")[-1200:]

    def _cleanup_old_sessions(self) -> None:
        if self.session_retention_days <= 0:
            return
        deadline = datetime.now() - timedelta(days=self.session_retention_days)
        for p in self.session_dir.glob("*.md"):
            try:
                dt = datetime.strptime(p.stem, "%Y-%m-%d")
            except ValueError:
                continue
            if dt < deadline:
                p.unlink(missing_ok=True)
