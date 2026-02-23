from __future__ import annotations

from flask import Flask, jsonify, request

from .config_loader import load_config
from .identity_loader import IdentityLoader
from .llm_server import LLMServer
from .query_board import QueryBoard
from .session_memory import SessionMemory
from .timeline_manager import TimelineManager
from .todo_board import TodoBoard
from .tool_manager import ToolManager
from .unified_loop import UnifiedLoop


def create_app(config_path: str = "config/config.yaml") -> Flask:
    config = load_config(config_path)
    query_board = QueryBoard()
    loop = UnifiedLoop(
        config=config,
        llm=LLMServer(config.model),
        identity_loader=IdentityLoader(config.identity),
        session_memory=SessionMemory(config.memory),
        timeline_manager=TimelineManager(config.timeline, config.breathing.soulbeat_timeline_threshold),
        query_board=query_board,
        tool_manager=ToolManager(query_board=query_board, todo_board=TodoBoard()),
    )
    loop.start()

    app = Flask(__name__)
    app.config["loop"] = loop

    @app.get("/health")
    def health() -> tuple[dict[str, str], int]:
        return {"status": "ok"}, 200

    @app.get("/status")
    def status() -> tuple[dict, int]:
        return jsonify(app.config["loop"].status()), 200

    @app.post("/query")
    def query() -> tuple[dict, int]:
        payload = request.get_json(force=True, silent=True) or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            return {"error": "text is required"}, 400
        return jsonify(app.config["loop"].submit_query(text, payload.get("metadata") or {})), 202

    @app.post("/camera")
    def camera() -> tuple[dict, int]:
        payload = request.get_json(force=True, silent=True) or {}
        image_ref = str(payload.get("image_ref", "")).strip()
        if not image_ref:
            return {"error": "image_ref is required"}, 400
        return jsonify(app.config["loop"].submit_camera_frame(image_ref)), 202

    @app.post("/react/toggle")
    def react_toggle() -> tuple[dict, int]:
        payload = request.get_json(force=True, silent=True) or {}
        enabled = bool(payload.get("enabled", True))
        return jsonify({"react_enabled": app.config["loop"].set_react_enabled(enabled)}), 200

    @app.post("/asr")
    def asr() -> tuple[dict, int]:
        payload = request.get_json(force=True, silent=True) or {}
        text = str(payload.get("text", "")).strip()
        if not text:
            return {"error": "text is required"}, 400
        return jsonify(app.config["loop"].submit_query(text, {"source": "asr"})), 202

    @app.post("/tts")
    def tts() -> tuple[dict, int]:
        payload = request.get_json(force=True, silent=True) or {}
        text = str(payload.get("text", "")).strip()
        return jsonify({"accepted": True, "text": text}), 200

    @app.teardown_appcontext
    def shutdown(_exc=None):
        loop.stop()

    return app
