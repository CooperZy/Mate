from __future__ import annotations

from pathlib import Path


class DocumentManager:
    def read_text(self, path: str | Path) -> str:
        return Path(path).read_text(encoding="utf-8")

