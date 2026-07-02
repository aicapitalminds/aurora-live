import json
import tempfile
import time
import unittest
from pathlib import Path

from aurora_gemini_session import GeminiLiveSessionStore


class GeminiLiveSessionStoreTests(unittest.TestCase):
    def test_update_and_reload_handle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = GeminiLiveSessionStore(path)
            self.assertTrue(store.update_handle("handle-a", model="model-a"))
            self.assertEqual(store.usable_handle(model="model-a"), "handle-a")

            reloaded = GeminiLiveSessionStore(path)
            self.assertEqual(reloaded.usable_handle(model="model-a"), "handle-a")
            self.assertEqual(reloaded.state.model, "model-a")

    def test_usable_handle_rejects_stale_or_wrong_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = GeminiLiveSessionStore(path, ttl_sec=1)
            store.update_handle("handle-a", model="model-a")
            self.assertIsNone(store.usable_handle(model="model-b"))
            store.state.handle_saved_at = time.time() - 5
            store.save()
            self.assertIsNone(store.usable_handle(model="model-a"))

    def test_record_go_away_and_clear_handle(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.json"
            store = GeminiLiveSessionStore(path)
            store.update_handle("handle-a", model="model-a")
            store.record_go_away("30s")
            self.assertEqual(store.state.last_go_away_time_left, "30s")
            store.clear_handle(reason="test")
            self.assertIsNone(store.usable_handle(model="model-a"))
            raw = json.loads(path.read_text())
            self.assertIn("recent_events", raw)


if __name__ == "__main__":
    unittest.main()
