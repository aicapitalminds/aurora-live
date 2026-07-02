import tempfile
import unittest
from pathlib import Path

from aurora_memory import AuroraMemoryStore


class AuroraMemoryStoreTests(unittest.TestCase):
    def test_bootstrap_creates_core_memory_files_and_loads_startup_context(self):
        with tempfile.TemporaryDirectory() as td:
            store = AuroraMemoryStore(Path(td))
            context = store.load_startup_memory(max_chars=4000)

            self.assertTrue((Path(td) / "SOUL.md").exists())
            self.assertTrue((Path(td) / "USER.md").exists())
            self.assertTrue((Path(td) / "MEMORY.md").exists())
            self.assertIn("Aurora", context)
            self.assertIn("Attila", context)

    def test_remember_note_persists_to_daily_and_curated_memory(self):
        with tempfile.TemporaryDirectory() as td:
            store = AuroraMemoryStore(Path(td))
            result = store.remember_note("Vision should default off unless Attila asks.", category="aurora")

            self.assertTrue(result["ok"])
            self.assertIn("Vision should default off", (Path(td) / "MEMORY.md").read_text(encoding="utf-8"))
            daily_files = list((Path(td) / "daily").glob("*.md"))
            self.assertEqual(len(daily_files), 1)
            self.assertIn("Vision should default off", daily_files[0].read_text(encoding="utf-8"))

    def test_recall_memory_returns_relevant_snippets(self):
        with tempfile.TemporaryDirectory() as td:
            store = AuroraMemoryStore(Path(td))
            store.remember_note("Native Google Search caused Gemini Live 1011 handshake loops.", category="pitfalls")
            store.remember_note("Weather connector uses Open-Meteo and works for Kendal UK.", category="tools")

            result = store.recall_memory("google search handshake")

            self.assertTrue(result["ok"])
            self.assertGreaterEqual(len(result["matches"]), 1)
            joined = "\n".join(match["text"] for match in result["matches"])
            self.assertIn("Google Search", joined)
            self.assertNotIn("Open-Meteo", joined)


if __name__ == "__main__":
    unittest.main()
