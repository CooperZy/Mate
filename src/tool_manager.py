from __future__ import annotations

import importlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from .query_board import QueryBoard, ToolTask
from .todo_board import TodoBoard

ToolFn = Callable[[dict[str, Any]], dict[str, Any]]


class ToolManager:
    def __init__(self, query_board: QueryBoard, todo_board: TodoBoard) -> None:
        self.query_board = query_board
        self.todo_board = todo_board
        self._executor = ThreadPoolExecutor(max_workers=4)
        self._tools: dict[str, ToolFn] = {}
        self.discover_and_register()

    def discover_and_register(self) -> None:
        self._tools["speak"] = self._speak
        self._tools["file_read"] = self._file_read
        self._tools["todo"] = self._todo
        self._tools["times"] = self._times
        self._tools["memory"] = self._memory
        self._tools["web_search"] = self._web_search
        self._optional_dynamic_discovery()

    def _optional_dynamic_discovery(self) -> None:
        for tool_file in Path("tools").glob("*/tool.py"):
            module_name = ".".join(tool_file.with_suffix("").parts)
            try:
                module = importlib.import_module(module_name)
                if hasattr(module, "execute"):
                    self._tools[tool_file.parent.name] = getattr(module, "execute")
            except Exception:
                continue

    def execute_tool_call(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        task = self.query_board.add_tool_call(name, arguments)
        if name == "speak":
            self.query_board.mark_running(task.id)
            try:
                result = self._run_tool(task)
                self.query_board.mark_done(task.id, result)
                return {"status": "done", "task_id": task.id, "result": result}
            except Exception as exc:
                self.query_board.mark_failed(task.id, str(exc))
                return {"status": "failed", "task_id": task.id, "error": str(exc)}

        self._executor.submit(self._run_async, task)
        return {"status": "executing", "task_id": task.id}

    def _run_async(self, task: ToolTask) -> None:
        self.query_board.mark_running(task.id)
        try:
            result = self._run_tool(task)
            self.query_board.mark_done(task.id, result)
        except Exception as exc:
            self.query_board.mark_failed(task.id, str(exc))

    def _run_tool(self, task: ToolTask) -> dict[str, Any]:
        tool = self._tools.get(task.name)
        if not tool:
            raise ValueError(f"unknown tool: {task.name}")
        return tool(task.arguments)

    @staticmethod
    def _speak(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"spoken": str(arguments.get("text", ""))}

    @staticmethod
    def _file_read(arguments: dict[str, Any]) -> dict[str, Any]:
        path = Path(arguments["path"])
        return {"path": str(path), "content": path.read_text(encoding="utf-8")}

    def _todo(self, arguments: dict[str, Any]) -> dict[str, Any]:
        action = arguments.get("action", "list")
        if action == "add":
            item = str(arguments.get("item", "")).strip()
            if item:
                self.todo_board.add(item)
            return {"items": self.todo_board.list()}
        return {"items": self.todo_board.list()}

    @staticmethod
    def _times(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"iso": datetime.utcnow().isoformat() + "Z", "echo_tz": arguments.get("tz", "UTC")}

    @staticmethod
    def _memory(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"status": "ok", "note": arguments.get("note", "")}

    @staticmethod
    def _web_search(arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", "")).strip()
        return {"query": query, "results": [f"stub:{query}"]}

