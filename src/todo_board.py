from __future__ import annotations

from threading import Lock


class TodoBoard:
    def __init__(self) -> None:
        self._lock = Lock()
        self._items: list[str] = []

    def add(self, item: str) -> None:
        with self._lock:
            self._items.append(item)

    def list(self) -> list[str]:
        with self._lock:
            return list(self._items)

