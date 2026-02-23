from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from src.config_loader import ModelConfig
from src.llm_server import LLMServer, LLMServerError


class LLMServerTests(unittest.TestCase):
    def test_complete_retries_with_sleep(self) -> None:
        server = LLMServer(ModelConfig(retries=2))

        bad_resp = Mock(status_code=500, text="boom")
        ok_resp = Mock(status_code=200)
        ok_resp.json.return_value = {"choices": [{"message": {"content": "ok"}}]}

        with patch("src.llm_server.requests") as req, patch("src.llm_server.time.sleep") as sleep:
            req.post.side_effect = [bad_resp, bad_resp, ok_resp]
            out = server.complete(messages=[{"role": "user", "content": "hi"}])

        self.assertEqual(out, "ok")
        self.assertEqual(sleep.call_count, 2)

    def test_complete_raises_when_requests_missing(self) -> None:
        server = LLMServer(ModelConfig())
        with patch("src.llm_server.requests", None):
            with self.assertRaises(LLMServerError):
                server.complete(messages=[])


if __name__ == "__main__":
    unittest.main()
