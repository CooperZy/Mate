from __future__ import annotations

import threading
import time
from collections import deque
from datetime import datetime
from typing import Any

from .config_loader import AppConfig
from .filter import filter_reply
from .identity_loader import IdentityLoader
from .llm_server import LLMServer, LLMServerError
from .query_board import QueryBoard
from .session_memory import SessionMemory
from .text_tool_parser import TextToolParser
from .timeline_manager import TimelineManager
from .tool_manager import ToolManager
from .types import DistillResult, LoopMode


class UnifiedLoop:
    def __init__(
        self,
        config: AppConfig,
        llm: LLMServer,
        identity_loader: IdentityLoader,
        session_memory: SessionMemory,
        timeline_manager: TimelineManager,
        query_board: QueryBoard,
        tool_manager: ToolManager,
    ) -> None:
        self.config = config
        self.llm = llm
        self.identity_loader = identity_loader
        self.session_memory = session_memory
        self.timeline_manager = timeline_manager
        self.query_board = query_board
        self.tool_manager = tool_manager
        self.parser = TextToolParser()

        self._react_enabled = True
        self._latest_frame: str | None = None
        self._inbox: deque[dict[str, Any]] = deque()
        self._last_soulbeat = time.monotonic()
        self._last_heartbeat = 0.0
        self._last_normal = 0.0
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._initial_summary = self.session_memory.load_recent_session_summary()

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
        self.identity_loader.close()

    def submit_query(self, text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        message = {"ts": datetime.now().isoformat(), "text": text, "metadata": metadata or {}}
        self._inbox.append(message)
        return {"status": "queued", "query_id": f"q-{int(time.time() * 1000)}"}

    def submit_camera_frame(self, image_ref: str) -> dict[str, Any]:
        self._latest_frame = image_ref
        entry = self.timeline_manager.add_entry(
            mode=LoopMode.HEARTBEAT,
            text="camera_frame",
            image_ref=image_ref,
        )
        return {"status": "ok", "frame_id": entry.id}

    def set_react_enabled(self, enabled: bool) -> bool:
        self._react_enabled = enabled
        return self._react_enabled

    def status(self) -> dict[str, Any]:
        return {
            "react_enabled": self._react_enabled,
            "pending_queries": len(self._inbox),
            "timeline_size": len(self.timeline_manager.entries()),
            "tool_tasks": self.query_board.status(),
        }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = time.monotonic()
            did_work = False

            if now - self._last_heartbeat >= self.config.breathing.heartbeat_interval:
                self._heartbeat_cycle()
                self._last_heartbeat = now
                did_work = True

            if now - self._last_normal >= self.config.breathing.normal_interval and self._inbox:
                self._normal_cycle(trigger="inbox")
                self._last_normal = now
                did_work = True

            if now - self._last_soulbeat >= self.config.breathing.soulbeat_interval:
                self._soulbeat_cycle()
                self._last_soulbeat = now
                did_work = True

            if not did_work:
                time.sleep(0.02)

    def _system_context(self) -> str:
        identity_prefix = self.identity_loader.load_prefix()
        return "\n\n".join(
            part for part in [identity_prefix, self._initial_summary, self.timeline_manager.summary] if part
        )

    def _timeline_brief(self, max_n: int = 8) -> str:
        entries = self.timeline_manager.entries()[-max_n:]
        lines = [f"[{e.id}] {e.mode.value} {e.text}" for e in entries]
        return "\n".join(lines)

    def _heartbeat_cycle(self) -> None:
        pending_results = self.query_board.pop_pending_results()
        prompt = (
            f"△\nTimeline:\n{self._timeline_brief()}\n"
            f"PendingToolResults:{pending_results}\n"
            "仅输出 <idle/> 或 <event ...> 或 <react/>"
        )
        parsed = self._ask_model(prompt, max_tokens=self.config.breathing.heartbeat_max_tokens)

        if parsed.event:
            self.timeline_manager.add_entry(
                mode=LoopMode.HEARTBEAT,
                text=parsed.event.text,
                event_type=parsed.event.type,
                tool_results=pending_results,
            )

        if self._react_enabled and parsed.react:
            self._normal_cycle(trigger="react")

    def _normal_cycle(self, trigger: str) -> None:
        message = self._inbox.popleft() if self._inbox else {"text": ""}
        prompt = (
            f"NormalReasoning trigger={trigger}\n"
            f"UserInput:{message.get('text', '')}\n"
            f"Timeline:\n{self._timeline_brief()}\n"
            "可用 tool_call。若无动作可回复 <idle/>"
        )
        parsed = self._ask_model(prompt, max_tokens=self.config.model.max_tokens)

        tool_exec_results: list[dict[str, Any]] = []
        for tc in parsed.tool_calls:
            tool_exec_results.append(self.tool_manager.execute_tool_call(tc.name, tc.arguments))

        final_reply = filter_reply(parsed.reply)
        if final_reply:
            self.timeline_manager.add_entry(
                mode=LoopMode.NORMAL,
                text=final_reply,
                tool_results=tool_exec_results,
            )

    def _soulbeat_cycle(self) -> None:
        if len(self.timeline_manager.entries()) < self.config.breathing.soulbeat_timeline_threshold:
            return
        prompt = (
            "◆\n请做结构化蒸馏:\n"
            "<distill><facts>..</facts><events>..</events><active>..</active><discard>..</discard></distill>\n"
            f"Timeline:\n{self._timeline_brief(max_n=24)}"
        )
        parsed = self._ask_model(prompt, max_tokens=self.config.breathing.soulbeat_max_tokens)
        distill = parsed.distill or DistillResult()
        self.session_memory.append_events(distill.events)
        self.session_memory.upsert_user_facts(distill.facts)
        self.timeline_manager.apply_distill(distill)
        self.timeline_manager.add_entry(mode=LoopMode.SOULBEAT, text="distilled")

    def _ask_model(self, prompt: str, max_tokens: int) -> Any:
        messages = [
            {"role": "system", "content": self._system_context()},
            {"role": "user", "content": prompt},
        ]
        try:
            raw = self.llm.complete(messages=messages, max_tokens=max_tokens)
        except LLMServerError:
            raw = "<idle/>"
        return self.parser.parse(raw)

