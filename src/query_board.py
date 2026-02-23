from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from time import monotonic
from typing import Any


@dataclass(slots=True)
class ToolTask:
    id: int
    name: str
    arguments: dict[str, Any]
    status: str = "pending"
    result: dict[str, Any] | None = None
    error: str | None = None
    created_monotonic: float = 0.0
    started_monotonic: float | None = None


class QueryBoard:
    def __init__(self) -> None:
        self._lock = Lock()
        self._next_id = 1
        self._tasks: dict[int, ToolTask] = {}
        self._pending_results: list[dict[str, Any]] = []

    def add_tool_call(self, name: str, arguments: dict[str, Any]) -> ToolTask:
        with self._lock:
            task = ToolTask(id=self._next_id, name=name, arguments=arguments, created_monotonic=monotonic())
            self._tasks[task.id] = task
            self._next_id += 1
            return task

    def mark_running(self, task_id: int) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.status = "running"
            task.started_monotonic = monotonic()

    def mark_done(self, task_id: int, result: dict[str, Any]) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.status = "done"
            task.result = result
            self._pending_results.append({"task_id": task_id, "name": task.name, "result": result})

    def mark_failed(self, task_id: int, error: str) -> None:
        with self._lock:
            task = self._tasks[task_id]
            task.status = "failed"
            task.error = error
            self._pending_results.append({"task_id": task_id, "name": task.name, "error": error})

    def has_pending_results(self) -> bool:
        with self._lock:
            return bool(self._pending_results)

    def peek_pending_results(self) -> list[dict[str, Any]]:
        with self._lock:
            return list(self._pending_results)

    def pop_pending_results(self) -> list[dict[str, Any]]:
        with self._lock:
            results = list(self._pending_results)
            self._pending_results.clear()
            return results

    def has_long_running_task(self, timeout_sec: float) -> bool:
        now = monotonic()
        with self._lock:
            for task in self._tasks.values():
                if task.status == "running" and task.started_monotonic is not None and now - task.started_monotonic >= timeout_sec:
                    return True
            return False

    def status(self) -> dict[str, int]:
        with self._lock:
            out = {"pending": 0, "running": 0, "done": 0, "failed": 0}
            for task in self._tasks.values():
                out[task.status] += 1
            out["pending_results"] = len(self._pending_results)
            return out
