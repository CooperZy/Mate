from __future__ import annotations

import unittest
from unittest.mock import Mock

from src.config_loader import AppConfig
from src.unified_loop import UnifiedLoop


class UnifiedLoopModeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.config = AppConfig()
        self.llm = Mock()
        self.identity_loader = Mock()
        self.identity_loader.load_prefix.return_value = ""
        self.identity_loader.close.return_value = None
        self.session_memory = Mock()
        self.session_memory.load_recent_session_summary.return_value = ""
        self.timeline_manager = Mock()
        self.timeline_manager.entries.return_value = []
        self.timeline_manager.summary = ""
        self.query_board = Mock()
        self.query_board.status.return_value = []
        self.query_board.has_pending_results.return_value = False
        self.query_board.has_long_running_task.return_value = False
        self.tool_manager = Mock()

        self.loop = UnifiedLoop(
            config=self.config,
            llm=self.llm,
            identity_loader=self.identity_loader,
            session_memory=self.session_memory,
            timeline_manager=self.timeline_manager,
            query_board=self.query_board,
            tool_manager=self.tool_manager,
        )

    def test_set_observation_mode_accepts_valid_values(self) -> None:
        self.assertEqual(self.loop.set_observation_mode("text_only"), "text_only")
        self.assertEqual(self.loop.config.breathing.observation_mode, "text_only")
        self.assertEqual(self.loop.set_observation_mode("off"), "off")
        self.assertEqual(self.loop.set_observation_mode("visual"), "visual")

    def test_set_observation_mode_invalid_value_raises(self) -> None:
        with self.assertRaises(ValueError):
            self.loop.set_observation_mode("invalid")

    def test_set_observation_mode_non_visual_clears_latest_frame(self) -> None:
        self.loop._latest_frame = "http://image"
        self.loop.set_observation_mode("text_only")
        self.assertIsNone(self.loop._latest_frame)

    def test_set_heartbeat_only_updates_flag(self) -> None:
        self.assertTrue(self.loop.set_heartbeat_only(True))
        self.assertFalse(self.loop.set_heartbeat_only(False))

    def test_effective_image_ref_respects_mode(self) -> None:
        self.loop._latest_frame = "http://image"
        self.loop.config.breathing.observation_mode = "visual"
        self.assertEqual(self.loop._effective_image_ref(), "http://image")
        self.loop.config.breathing.observation_mode = "off"
        self.assertIsNone(self.loop._effective_image_ref())

    def test_observation_payload_matches_mode(self) -> None:
        self.loop.config.breathing.observation_mode = "visual"
        self.assertIn("visual frame", self.loop._observation_payload())
        self.loop.config.breathing.observation_mode = "text_only"
        self.assertIn("text-only heartbeat", self.loop._observation_payload())
        self.loop.config.breathing.observation_mode = "off"
        self.assertIn("no observation", self.loop._observation_payload())

    def test_should_run_normal_cycle_when_heartbeat_only(self) -> None:
        self.loop.config.breathing.heartbeat_only = True
        self.loop.config.breathing.normal_interval = 1.0
        self.loop._last_normal = 0.0
        self.assertFalse(self.loop._should_run_normal_cycle(0.5))
        self.loop._inbox.append({"text": "hello"})
        self.assertTrue(self.loop._should_run_normal_cycle(1.1))

    def test_should_run_normal_cycle_handles_pending_results_when_not_heartbeat_only(self) -> None:
        self.loop.config.breathing.heartbeat_only = False
        self.loop.config.breathing.normal_interval = 1.0
        self.loop._last_normal = 0.0
        self.loop._pending_results_buffer.append({"status": "done"})
        self.assertTrue(self.loop._should_run_normal_cycle(1.1))


if __name__ == "__main__":
    unittest.main()
