from __future__ import annotations

from pathlib import Path

from .config_loader import IdentityConfig

try:
    from watchdog.events import FileSystemEventHandler
    from watchdog.observers import Observer
except Exception:  # pragma: no cover
    FileSystemEventHandler = object  # type: ignore[assignment]
    Observer = None  # type: ignore[assignment]


class _IdentityChangeHandler(FileSystemEventHandler):  # type: ignore[misc]
    def __init__(self, loader: "IdentityLoader") -> None:
        self.loader = loader

    def on_modified(self, event):  # type: ignore[no-untyped-def]
        if not event.is_directory:
            self.loader.prefix_dirty = True

    def on_created(self, event):  # type: ignore[no-untyped-def]
        if not event.is_directory:
            self.loader.prefix_dirty = True


class IdentityLoader:
    ORDER = ["SOUL.md", "AGENT.md", "TOOLS.md", "KNOWLEDGE.md", "USER.md"]

    def __init__(self, config: IdentityConfig) -> None:
        self.identity_dir = Path(config.directory)
        self.identity_dir.mkdir(parents=True, exist_ok=True)
        self.hot_reload = config.hot_reload
        self.prefix_dirty = True
        self._cached_prefix = ""
        self._observer = None
        if self.hot_reload and Observer is not None:
            self._start_watch()

    def _start_watch(self) -> None:
        self._observer = Observer()
        handler = _IdentityChangeHandler(self)
        self._observer.schedule(handler, str(self.identity_dir), recursive=False)
        self._observer.daemon = True
        self._observer.start()

    def close(self) -> None:
        if self._observer is not None:
            self._observer.stop()
            self._observer.join(timeout=1.0)

    def load_prefix(self, force: bool = False) -> str:
        if not force and not self.prefix_dirty and self._cached_prefix:
            return self._cached_prefix
        docs: list[str] = []
        for filename in self.ORDER:
            path = self.identity_dir / filename
            if path.exists():
                docs.append(path.read_text(encoding="utf-8").strip())
        self._cached_prefix = "\n\n".join(part for part in docs if part).strip()
        self.prefix_dirty = False
        return self._cached_prefix

