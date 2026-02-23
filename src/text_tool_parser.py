from __future__ import annotations

import json
import re
from html import unescape

from .types import DistillResult, ParsedModelOutput, TimelineEvent, ToolCall

_TOOL_CALL_RE = re.compile(r"<tool_call>\s*(\{.*?\})\s*</tool_call>", re.DOTALL)
_EVENT_RE = re.compile(r'<event\s+type="([^"]+)">(.*?)</event>', re.DOTALL)
_DISTILL_RE = re.compile(r"<distill>(.*?)</distill>", re.DOTALL)
_TAG_FIELD_TEMPLATE = r"<{name}>(.*?)</{name}>"


class TextToolParser:
    def parse(self, text: str) -> ParsedModelOutput:
        raw = text or ""
        out = ParsedModelOutput(reply=raw.strip())

        if "<idle/>" in raw or "<idle>" in raw:
            out.idle = True
        if "<react/>" in raw or "<react>" in raw:
            out.react = True

        event_match = _EVENT_RE.search(raw)
        if event_match:
            out.event = TimelineEvent(
                type=event_match.group(1).strip(),
                text=unescape(event_match.group(2).strip()),
            )

        distill_match = _DISTILL_RE.search(raw)
        if distill_match:
            body = distill_match.group(1)
            out.distill = DistillResult(
                facts=self._extract_list(body, "facts"),
                events=self._extract_list(body, "events"),
                active=self._extract_list(body, "active"),
                discard=self._extract_list(body, "discard"),
            )

        for match in _TOOL_CALL_RE.finditer(raw):
            payload = match.group(1)
            try:
                data = json.loads(payload)
                name = str(data.get("name", "")).strip()
                arguments = data.get("arguments") or {}
                if name:
                    out.tool_calls.append(ToolCall(name=name, arguments=arguments))
            except json.JSONDecodeError:
                continue

        cleaned = _TOOL_CALL_RE.sub("", raw)
        cleaned = _EVENT_RE.sub("", cleaned)
        cleaned = _DISTILL_RE.sub("", cleaned)
        cleaned = cleaned.replace("<idle/>", "").replace("<react/>", "")
        out.reply = cleaned.strip()
        return out

    @staticmethod
    def _extract_list(body: str, name: str) -> list[str]:
        m = re.search(_TAG_FIELD_TEMPLATE.format(name=name), body, re.DOTALL)
        if not m:
            return []
        content = m.group(1).strip()
        if not content:
            return []
        parts = [p.strip(" -\t\r\n") for p in content.splitlines()]
        return [p for p in parts if p]

