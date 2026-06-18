"""Runtime bridge from Aurora voice backend to Unreal MetaHuman.

This module intentionally stays independent from Unreal MCP. MCP is for editor
automation; this bridge is for high-frequency runtime avatar state and lip-sync
events consumed by an Unreal-side WebSocket client/controller.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
import json
import logging
import time
from typing import Any

import websockets


class AuroraAvatarState(str, Enum):
    IDLE = "idle"
    LISTENING = "listening"
    THINKING = "thinking"
    SPEAKING = "speaking"


def normalize_state(state: str | AuroraAvatarState) -> AuroraAvatarState:
    if isinstance(state, AuroraAvatarState):
        return state
    try:
        return AuroraAvatarState(str(state).lower())
    except ValueError as exc:
        valid = ", ".join(s.value for s in AuroraAvatarState)
        raise ValueError(f"Unknown Aurora avatar state {state!r}; valid states: {valid}") from exc


def _timestamp(value: float | None = None) -> float:
    return time.time() if value is None else float(value)


def build_state_event(state: str | AuroraAvatarState, timestamp: float | None = None) -> dict[str, Any]:
    normalized = normalize_state(state)
    return {
        "type": "avatar.state",
        "state": normalized.value,
        "timestamp": _timestamp(timestamp),
    }


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def build_lipsync_event(values: list[float] | tuple[float, ...], window_ms: int, timestamp: float | None = None) -> dict[str, Any]:
    return {
        "type": "avatar.lipsync.amplitude",
        "windowMs": int(window_ms),
        "values": [_clamp01(v) for v in values],
        "timestamp": _timestamp(timestamp),
    }


def build_text_event(text: str, partial: bool = False, timestamp: float | None = None) -> dict[str, Any]:
    return {
        "type": "avatar.text.partial" if partial else "avatar.text.final",
        "text": text,
        "timestamp": _timestamp(timestamp),
    }


def build_gesture_event(name: str, intensity: float = 1.0, timestamp: float | None = None) -> dict[str, Any]:
    return {
        "type": "avatar.gesture",
        "name": name,
        "intensity": _clamp01(intensity),
        "timestamp": _timestamp(timestamp),
    }


@dataclass
class UnrealAvatarBridge:
    host: str = "127.0.0.1"
    port: int = 8771
    logger: logging.Logger = field(default_factory=lambda: logging.getLogger("AuroraUnrealBridge"))
    clients: set[Any] = field(default_factory=set)
    current_state: AuroraAvatarState = AuroraAvatarState.IDLE
    server: Any | None = None

    async def handler(self, websocket):
        self.clients.add(websocket)
        self.logger.info("🎭 Unreal avatar client connected (%s total)", len(self.clients))
        try:
            await websocket.send(json.dumps(build_state_event(self.current_state), separators=(",", ":")))
            async for raw in websocket:
                # The Unreal side may send pings/acks/control messages later. Keep
                # handling permissive so experimental controllers don't kill the bridge.
                self.logger.debug("Unreal avatar client message: %s", str(raw)[:300])
        finally:
            self.clients.discard(websocket)
            self.logger.info("🎭 Unreal avatar client disconnected (%s total)", len(self.clients))

    async def start(self):
        if self.server is not None:
            return self.server
        self.server = await websockets.serve(self.handler, self.host, self.port)
        self.logger.info("🎭 Unreal avatar bridge WebSocket started on ws://%s:%s", self.host, self.port)
        return self.server

    async def stop(self):
        if self.server is None:
            return
        self.server.close()
        await self.server.wait_closed()
        self.server = None

    async def broadcast(self, event: dict[str, Any]) -> None:
        if not self.clients:
            return
        payload = json.dumps(event, separators=(",", ":"))
        dead = []
        for client in list(self.clients):
            try:
                await client.send(payload)
            except Exception:
                dead.append(client)
                self.logger.exception("Failed to send Unreal avatar event; dropping client")
        for client in dead:
            self.clients.discard(client)

    async def set_state(self, state: str | AuroraAvatarState, *, force: bool = False, timestamp: float | None = None) -> None:
        normalized = normalize_state(state)
        if not force and normalized == self.current_state:
            return
        self.current_state = normalized
        await self.broadcast(build_state_event(normalized, timestamp=timestamp))

    async def send_lipsync(self, values: list[float] | tuple[float, ...], window_ms: int, *, timestamp: float | None = None) -> None:
        await self.broadcast(build_lipsync_event(values, window_ms=window_ms, timestamp=timestamp))

    async def send_text(self, text: str, *, partial: bool = False, timestamp: float | None = None) -> None:
        await self.broadcast(build_text_event(text, partial=partial, timestamp=timestamp))

    async def send_gesture(self, name: str, *, intensity: float = 1.0, timestamp: float | None = None) -> None:
        await self.broadcast(build_gesture_event(name, intensity=intensity, timestamp=timestamp))


async def safe_set_state(bridge: UnrealAvatarBridge | None, state: str | AuroraAvatarState, **kwargs) -> None:
    if bridge is None:
        return
    try:
        await bridge.set_state(state, **kwargs)
    except Exception:
        bridge.logger.exception("Unreal avatar state update failed")


async def safe_send_lipsync(bridge: UnrealAvatarBridge | None, values: list[float] | tuple[float, ...], window_ms: int) -> None:
    if bridge is None:
        return
    try:
        await bridge.send_lipsync(values, window_ms)
    except Exception:
        bridge.logger.exception("Unreal avatar lip-sync update failed")
