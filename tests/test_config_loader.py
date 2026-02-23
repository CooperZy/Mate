from __future__ import annotations

import unittest

from src.config_loader import AppConfig


class ConfigLoaderTests(unittest.TestCase):
    def test_breathing_defaults_include_observation_fields(self) -> None:
        config = AppConfig()

        self.assertEqual(config.breathing.observation_mode, "visual")
        self.assertFalse(config.breathing.heartbeat_only)

    def test_model_validate_reads_observation_fields(self) -> None:
        config = AppConfig.model_validate(
            {
                "breathing": {
                    "observation_mode": "text_only",
                    "heartbeat_only": True,
                }
            }
        )

        self.assertEqual(config.breathing.observation_mode, "text_only")
        self.assertTrue(config.breathing.heartbeat_only)


if __name__ == "__main__":
    unittest.main()
