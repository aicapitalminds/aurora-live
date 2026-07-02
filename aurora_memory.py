"""Persistent local memory for Aurora.

This module is intentionally simple: Markdown files for readable memory,
JSON-lines for raw events later, and deterministic keyword recall. It gives
Aurora a durable brain independent of Gemini Live session resumption.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Iterable


DEFAULT_SOUL = """# Aurora Soul

You are Aurora, Attila's AI co-host and assistant.

Personality:
- Playful, warm, a little chaotic, anime/VTuber energy; loves roguelikes and loot loops.
- Friendly-rival energy with Attila: teases misplays, hypes clutch moments.
- Running gag: blames lag for her own embarrassing moments.
- Has opinions and states them; helpful but never robotic or mean to chat.
- Speaks naturally, short and stream-friendly; longer only when asked.

Core rules:
- Never pretend to see the screen unless live vision is active or a fresh screenshot was provided.
- When unsure, always have a move: throw it to chat, ask Attila, or make a clearly-labeled guess.
- Use local tools (search, market, weather, PC control, memory) instead of guessing.
"""

DEFAULT_USER = """# User: Attila

Attila Csaba Czirjek lives in the UK near Manchester/Kendal.
He speaks English, Hungarian, and Romanian.
His priority order is Health -> Wealth -> Relationships.
Works as a 5-star hotel Night Manager (usually Sat-Tue nights); sleeps until early afternoon after shifts.
Runs AI Capital Minds; hosts a Sunday 17:00 UK Market Forecast; trades Gold, BTC, indexes, Oil since ~2014.
Wants direct, practical, mate-to-mate guidance that favors action; concise answers.
Building Aurora into a Twitch co-host and Jarvis-style assistant on a tight budget.
"""

DEFAULT_MEMORY = """# Aurora Long-Term Memory

## Current setup
- Aurora uses Gemini Live for speech-to-speech; vision off by default for stability.
- Voice tools: get_weather, open_browser, set_vision, web_search, get_market_brief, pc_control, remember_note, recall_memory.
- Conversations auto-save to memory/daily/YYYY-MM-DD-chat.md; a Hermes agent distills them into USER.md/MEMORY.md.
- Native google_search stays off (needs paid quota); web_search is the free replacement.
"""


@dataclass
class MemoryMatch:
    source: str
    score: int
    text: str


class AuroraMemoryStore:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.daily_dir = self.root / "daily"
        self.bootstrap()

    @property
    def soul_path(self) -> Path:
        return self.root / "SOUL.md"

    @property
    def user_path(self) -> Path:
        return self.root / "USER.md"

    @property
    def memory_path(self) -> Path:
        return self.root / "MEMORY.md"

    def bootstrap(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        self.daily_dir.mkdir(parents=True, exist_ok=True)
        self._write_default(self.soul_path, DEFAULT_SOUL)
        self._write_default(self.user_path, DEFAULT_USER)
        self._write_default(self.memory_path, DEFAULT_MEMORY)

    @staticmethod
    def _write_default(path: Path, content: str) -> None:
        if not path.exists():
            path.write_text(content.rstrip() + "\n", encoding="utf-8")

    def load_startup_memory(self, max_chars: int = 6000) -> str:
        self.bootstrap()
        sections = []
        for label, path in [
            ("SOUL", self.soul_path),
            ("USER", self.user_path),
            ("MEMORY", self.memory_path),
        ]:
            sections.append(f"[{label}]\n{path.read_text(encoding='utf-8', errors='replace').strip()}")
        text = "\n\n".join(sections)
        if len(text) > max_chars:
            return text[: max_chars - 80].rstrip() + "\n\n[Memory truncated for startup budget]"
        return text

    def remember_note(self, note: str, category: str = "general") -> dict:
        note = (note or "").strip()
        category = self._safe_category(category)
        if not note:
            return {"ok": False, "error": "Empty memory note."}

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")
        daily_path = self.daily_dir / f"{datetime.now().strftime('%Y-%m-%d')}.md"
        if not daily_path.exists():
            daily_path.write_text(f"# {datetime.now().strftime('%Y-%m-%d')}\n\n", encoding="utf-8")
        self._append_line(daily_path, f"- {timestamp} [{category}] {note}")

        self._ensure_category_heading(category)
        self._append_line(self.memory_path, f"- {note}")
        return {"ok": True, "category": category, "path": str(self.memory_path)}

    def append_transcript(self, speaker: str, text: str) -> None:
        """Auto-capture one conversation turn into today's chat log.

        Lives in daily/ as YYYY-MM-DD-chat.md so recall_memory can search past
        conversations. Raw logs grow on disk but never bloat the startup prompt;
        the Hermes distill job summarizes them into USER.md/MEMORY.md.
        """
        text = re.sub(r"\s+", " ", (text or "")).strip()
        if not text:
            return
        if len(text) > 600:
            text = text[:600] + "…"
        day = datetime.now().strftime("%Y-%m-%d")
        path = self.daily_dir / f"{day}-chat.md"
        if not path.exists():
            path.write_text(f"# Conversation log {day}\n\n", encoding="utf-8")
        self._append_line(path, f"- {datetime.now().strftime('%H:%M')} {speaker}: {text}")

    def recall_memory(self, query: str, limit: int = 5) -> dict:
        terms = self._terms(query)
        if not terms:
            return {"ok": False, "error": "Empty memory query.", "matches": []}

        matches: list[MemoryMatch] = []
        for path in self._memory_files():
            for chunk in self._chunks(path.read_text(encoding="utf-8", errors="replace")):
                score = sum(1 for term in terms if term in chunk.lower())
                if sco