import importlib.util
import tempfile
import unittest
from pathlib import Path


class AuroraLiveMemoryIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("aurora_live_mod", Path(__file__).resolve().parents[1] / "aurora-live.py")
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_live_tools_include_memory_functions(self):
        tools = self.mod.build_live_tools()
        names = [f.name for tool in tools for f in (tool.function_declarations or [])]
        self.assertIn("remember_note", names)
        self.assertIn("recall_memory", names)

    def test_current_system_prompt_includes_startup_memory(self):
        with tempfile.TemporaryDirectory() as td:
            old_store = self.mod.aurora_memory_store
            try:
                self.mod.aurora_memory_store = self.mod.AuroraMemoryStore(Path(td))
                self.mod.aurora_memory_store.remember_note("Aurora memory integration test marker.", category="test")
                prompt = self.mod.current_system_prompt()
            finally:
                self.mod.aurora_memory_store = old_store

        self.assertIn("Long-term memory", prompt)
        self.assertIn("Aurora memory integration test marker", prompt)


if __name__ == "__main__":
    unittest.main()
