from __future__ import annotations

import unittest

from src.config_loader import TimelineConfig
from src.timeline_manager import TimelineManager
from src.types import LoopMode


class TimelineManagerTests(unittest.TestCase):
    def test_should_distill_precedence_and_behavior(self) -> None:
        manager = TimelineManager(config=TimelineConfig(), distill_threshold=2)

        self.assertFalse(manager.should_distill(elapsed_sec=1.0, has_long_running_query=False))

        manager.add_entry(mode=LoopMode.HEARTBEAT, text="a")
        manager.add_entry(mode=LoopMode.HEARTBEAT, text="b")
        self.assertTrue(manager.should_distill(elapsed_sec=1.0, has_long_running_query=False))

        manager = TimelineManager(config=TimelineConfig(), distill_threshold=99)
        self.assertTrue(manager.should_distill(elapsed_sec=0.0, has_long_running_query=True))


if __name__ == "__main__":
    unittest.main()
