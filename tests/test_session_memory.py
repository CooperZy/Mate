from __future__ import annotations

import tempfile
import unittest

from src.config_loader import MemoryConfig
from src.session_memory import SessionMemory


class SessionMemoryTests(unittest.TestCase):
    def test_upsert_user_facts_deduplicates_stably(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            mem = SessionMemory(
                MemoryConfig(
                    session_dir=f"{tmp}/sessions",
                    user_facts_file=f"{tmp}/user_facts.md",
                    session_retention_days=30,
                )
            )
            mem.upsert_user_facts(["Likes tea", "likes tea", "  Likes tea  ", "Plays chess"])
            mem.upsert_user_facts(["plays chess", "Runs marathons"])

            lines = mem.user_facts_file.read_text(encoding="utf-8").splitlines()
            bullets = [line for line in lines if line.startswith("- ")]

            self.assertEqual(bullets, ["- Likes tea", "- Plays chess", "- Runs marathons"])


if __name__ == "__main__":
    unittest.main()
