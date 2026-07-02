"""Durable Gemini Live session state helpers for Aurora.

This module is intentionally SDK-light: it stores the opaque server-provided
session resumption handle and reconnect metadata, while aurora-live.py owns the
actual google.genai LiveConnectConfig construction.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import time
from pathlib import Path
from typing import Any


DEFAULT_HANDLE_TTL_SEC = 2 * 60 * 60  # Google docs: resumption tokens valid ~2h.


@dataclass
class GeminiLiveSessionState:
    handle: str | None = None
    handle_saved_at: float = 0.0
    model: str | None = None
    generation: int = 0
    last_go_away_at: float = 0.0
    last_go_away_time_left: str | None = None
    recent_events: list[dict[str, Any]] = field(default_factory=list)


class GeminiLiveSessionStore:
    """Persist and validate the latest Gemini Live session resumption handle."""

    def __init__(self, path: str | Path = "aurora-gemini-session-state.json", *, ttl_sec: int = DEFAULT_HANDLE_TTL_SEC):
        self.path = Path(path)
        self.ttl_sec = int(ttl_sec)
        self.state = GeminiLiveSessionState()
        self.load()

    def load(self) -> GeminiLiveSessionState:
        if not self.path.exists():
            return self.state
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
            self.state = GeminiLiveSessionState(
                handle=raw.get("handle"),
                handle_saved_at=float(raw.get("handle_saved_at") or 0.0),
                model=raw.get("model"),
                generation=int(raw.get("generation") or 0),
                last_go_away_at=float(raw.get("last_go_away_at") or 0.0),
                last_go_away_time_left=raw.get("last_go_away_time_left"),
                recent_events=list(raw.get("recent_events") or [])[-20:],
            )
        except Exception:
            # Corrupt state should never prevent Aurora from booting. Start fresh.
            self.state = GeminiLiveSessionState()
        return self.state

    def save(self) -> None:
        self.path.write_text(json.dumps(asdict(self.state), indent=2, sort_keys=True), encoding="utf-8")

    def _event(self, event_type: str, **fields: Any) -> None:
        self.state.recent_events.append({"type": event_type, "timestamp": time.time(), **fields})
        self.state.recent_events = self.state.recent_events[-20:]

    def usable_handle(self, *, model: str | None = None) -> str | None:
        """Return the current handle only if it is not stale and model-compatible."""
        handle = self.state.handle
        if not handle:
            return None
        if model and self.state.model and self.state.model != model:
            return None
        age = time.time() - float(self.state.handle_saved_at or 0.0)
        if age < 0 or age > self.ttl_sec:
            return None
        return handle

    def update_handle(self, handle: str, *, model: str | None = None) -> bool:
        """Persist a new opaque server handle. Returns True if it changed."""
        if not handle:
            return False
        changed = handle != self.state.handle
        self.state.handle = handle
        self.state.handle_saved_at = time.time()
        self.state.model = model or self.state.model
        if changed:
            self.state.generation += 1
            self._event("session_resumption_update", generation=self.state.generation, model=self.state.model)
        self.save()
        return changed

    def record_go_away(self, time_left: Any) -> None:
        self.state.last_go_away_at = time.time()
        self.state.last_go_away_time_left = str(time_left)
        self._event("go_away", time_left=str(time_left))
        self.save()

    def clear_handle(self, *, reason: str) -> None:
        self.state.handle = None
        self.state.handle_saved_at = 0.0
        self._event("clear_handle", reason=reason)
        self.save()
