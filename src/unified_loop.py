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
    MAX_PENDING_RESULTS_BUFFER = 200

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

        self._state_lock = threading.Lock()
        self._react_enabled = True
        self._latest_frame: str | None = None
        self._inbox: deque[dict[str, Any]] = deque()
        self._pending_results_buffer: list[dict[str, Any]] = []
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
        with self._state_lock:
            self._inbox.append(message)
        return {"status": "queued", "query_id": f"q-{int(time.time() * 1000)}"}

    def submit_camera_frame(self, image_ref: str) -> dict[str, Any]:
        with self._state_lock:
            self._latest_frame = image_ref
        return {"status": "ok", "frame": image_ref}

    def set_react_enabled(self, enabled: bool) -> bool:
        with self._state_lock:
            self._react_enabled = enabled
            return self._react_enabled

    def set_observation_mode(self, mode: str) -> str:
        if mode not in {"visual", "text_only", "off"}:
            raise ValueError("mode must be one of: visual, text_only, off")
        self.config.breathing.observation_mode = mode
        if mode != "visual":
            with self._state_lock:
                self._latest_frame = None
        return self.config.breathing.observation_mode

    def set_heartbeat_only(self, enabled: bool) -> bool:
        self.config.breathing.heartbeat_only = enabled
        return self.config.breathing.heartbeat_only

    def set_observation_mode(self, mode: str) -> str:
        if mode not in {"visual", "text_only", "off"}:
            raise ValueError("mode must be one of: visual, text_only, off")
        self.config.breathing.observation_mode = mode
        if mode != "visual":
            self._latest_frame = None
        return self.config.breathing.observation_mode

    def set_heartbeat_only(self, enabled: bool) -> bool:
        self.config.breathing.heartbeat_only = enabled
        return self.config.breathing.heartbeat_only

    def status(self) -> dict[str, Any]:
        with self._state_lock:
            pending_queries = len(self._inbox)
            has_frame = bool(self._latest_frame)
            react_enabled = self._react_enabled
            pending_results_size = len(self._pending_results_buffer)
        return {
            "react_enabled": self._react_enabled,
            "observation_mode": self.config.breathing.observation_mode,
            "heartbeat_only": self.config.breathing.heartbeat_only,
            "pending_queries": len(self._inbox),
            "timeline_size": len(self.timeline_manager.entries()),
            "tool_tasks": self.query_board.status(),
            "pending_tool_results_buffer": pending_results_size,
            "has_frame": has_frame,
            "last_soulbeat_sec": round(time.monotonic() - self._last_soulbeat, 2),
        }

    def _run(self) -> None:
        while not self._stop_event.is_set():
            now = time.monotonic()
            did_work = False
            self._drain_pending_results()

            if self._should_run_normal_cycle(now):
                trigger = "tool_result" if self._pending_results_buffer else "inbox"
                self._normal_cycle(trigger=trigger)
                self._last_normal = now
                did_work = True
            elif self._soulbeat_due(now):
                self._soulbeat_cycle()
                self._last_soulbeat = now
                did_work = True

            if not did_work:
                time.sleep(0.02)

    def _should_run_normal_cycle(self, now: float) -> bool:
        if self.config.breathing.heartbeat_only:
            return bool(self._inbox) and now - self._last_normal >= self.config.breathing.normal_interval
        if self._pending_results_buffer and now - self._last_normal >= self.config.breathing.normal_interval:
            return True
        return bool(self._inbox) and now - self._last_normal >= self.config.breathing.normal_interval

    def _drain_pending_results(self) -> None:
        if not self.query_board.has_pending_results():
            return
        popped = self.query_board.pop_pending_results()
        with self._state_lock:
            self._pending_results_buffer.extend(popped)
        self._trim_pending_results_buffer()

    def _soulbeat_due(self, now: float) -> bool:
        elapsed = now - self._last_soulbeat
        return self.timeline_manager.should_distill(
            elapsed_sec=elapsed,
            has_long_running_query=self.query_board.has_long_running_task(self.config.breathing.soulbeat_interval),
        )

    def _system_context(self) -> str:
        identity_prefix = self.identity_loader.load_prefix()
        return "\n\n".join(
            part for part in [identity_prefix, self._initial_summary, self.timeline_manager.summary] if part
        )

    def _timeline_brief(self, max_n: int = 8) -> str:
        entries = self.timeline_manager.entries()[-max_n:]
        lines = [f"[{e.id}] {e.mode.value} {e.text}" for e in entries]
        return "\n".join(lines)

    def _observation_payload(self) -> str:
        mode = self.config.breathing.observation_mode
        if mode == "visual":
            return "Observation: visual frame attached when available."
        if mode == "text_only":
            return (
                "Observation: text-only heartbeat (no image). "
                "Infer urgency only from timeline and pending tool results."
            )
        return "Observation: off (no observation). Emit <idle/> unless pending results imply action."

    def _effective_image_ref(self) -> str | None:
        if self.config.breathing.observation_mode != "visual":
            return None
        return self._latest_frame

    def _heartbeat_cycle(self) -> None:
        pending_results = self._pending_results_snapshot()
        prompt = (
            f"△\n{self._observation_payload()}\n"
            f"Timeline:\n{self._timeline_brief()}\n"
            f"PendingToolResults:{self._pending_results_buffer}\n"
            "仅输出 <idle/> 或 <event ...> 或 <react/>"
        )
        parsed = self._ask_model(prompt, max_tokens=self.config.breathing.heartbeat_max_tokens)

        heartbeat_text = "<idle/>"
        event_type = None
        if parsed.event:
            heartbeat_text = parsed.event.text
            event_type = parsed.event.type
        elif parsed.react:
            heartbeat_text = "<react/>"

        self.timeline_manager.add_entry(
            mode=LoopMode.HEARTBEAT,
            text=heartbeat_text,
            event_type=event_type,
            image_ref=self._effective_image_ref(),
            tool_results=list(self._pending_results_buffer),
        )

        if self._react_enabled and parsed.react and not self.config.breathing.heartbeat_only:
            self._normal_cycle(trigger="react")

    def _normal_cycle(self, trigger: str) -> None:
        with self._state_lock:
            message = self._inbox.popleft() if self._inbox else {"text": "", "metadata": {}}
            pending_results = list(self._pending_results_buffer)

        prompt = (
            f"NormalReasoning trigger={trigger}\n"
            f"UserInput:{message.get('text', '')}\n"
            f"ObservationMode:{self.config.breathing.observation_mode}\n"
            f"PendingToolResults:{self._pending_results_buffer}\n"
            f"Timeline:\n{self._timeline_brief(max_n=24)}\n"
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
                image_ref=self._effective_image_ref(),
                tool_results=tool_exec_results + list(self._pending_results_buffer),
            )

        with self._state_lock:
            # Keep only the items seen by this cycle removed; retain concurrently-added items.
            remove_count = min(len(self._pending_results_buffer), len(pending_results))
            if remove_count:
                del self._pending_results_buffer[:remove_count]
        self._trim_pending_results_buffer()

    def _soulbeat_cycle(self) -> None:
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
        self.timeline_manager.add_entry(mode=LoopMode.SOULBEAT, text="distilled", image_ref=self._effective_image_ref())

    def _ask_model(self, prompt: str, max_tokens: int) -> Any:
        messages = [
            {"role": "system", "content": self._system_context()},
            self.llm.build_user_message(prompt, self._effective_image_ref()),
        ]
        try:
            raw = self.llm.complete(messages=messages, max_tokens=max_tokens)
        except LLMServerError:
            raw = "<idle/>"
        return self.parser.parse(raw)
