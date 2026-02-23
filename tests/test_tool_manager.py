from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.query_board import QueryBoard
from src.todo_board import TodoBoard
from src.tool_manager import ToolManager


class ToolManagerTests(unittest.TestCase):
    def test_file_read_blocks_path_traversal(self) -> None:
        manager = ToolManager(QueryBoard(), TodoBoard())
        with self.assertRaises(ValueError):
            manager._file_read({"path": "../../etc/passwd"})

    def test_file_read_allows_repo_relative_file(self) -> None:
        manager = ToolManager(QueryBoard(), TodoBoard())
        with tempfile.TemporaryDirectory(dir=Path.cwd()) as tmp:
            p = Path(tmp) / "note.txt"
            p.write_text("ok", encoding="utf-8")
            rel = p.relative_to(Path.cwd())
            out = manager._file_read({"path": str(rel)})
            self.assertEqual(out["content"], "ok")


if __name__ == "__main__":
    unittest.main()
