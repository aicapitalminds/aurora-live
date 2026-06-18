import asyncio
import json
import unittest

from aurora_unreal_bridge import (
    AuroraAvatarState,
    UnrealAvatarBridge,
    build_lipsync_event,
    build_state_event,
    normalize_state,
)


class FakeClient:
    def __init__(self):
        self.messages = []
        self.closed = False

    async def send(self, payload):
        self.messages.append(json.loads(payload))


class UnrealBridgeTests(unittest.IsolatedAsyncioTestCase):
    def test_normalize_state_accepts_valid_values(self):
        self.assertEqual(normalize_state("speaking"), AuroraAvatarState.SPEAKING)
        self.assertEqual(normalize_state(AuroraAvatarState.LISTENING), AuroraAvatarState.LISTENING)

    def test_normalize_state_rejects_unknown_values(self):
        with self.assertRaises(ValueError):
            normalize_state("dancing")

    def test_state_event_schema(self):
        event = build_state_event("thinking", timestamp=123.4)
        self.assertEqual(event["type"], "avatar.state")
        self.assertEqual(event["state"], "thinking")
        self.assertEqual(event["timestamp"], 123.4)

    def test_lipsync_event_schema_clamps_values(self):
        event = build_lipsync_event([-1, 0.25, 2], window_ms=50, timestamp=5)
        self.assertEqual(event["type"], "avatar.lipsync.amplitude")
        self.assertEqual(event["values"], [0.0, 0.25, 1.0])
        self.assertEqual(event["windowMs"], 50)

    async def test_broadcast_sends_json_to_all_clients(self):
        bridge = UnrealAvatarBridge()
        c1, c2 = FakeClient(), FakeClient()
        bridge.clients.update({c1, c2})
        await bridge.broadcast({"type": "avatar.test", "value": 42})
        self.assertEqual(c1.messages, [{"type": "avatar.test", "value": 42}])
        self.assertEqual(c2.messages, [{"type": "avatar.test", "value": 42}])

    async def test_set_state_deduplicates_unless_forced(self):
        bridge = UnrealAvatarBridge()
        client = FakeClient()
        bridge.clients.add(client)
        await bridge.set_state("speaking", timestamp=1)
        await bridge.set_state("speaking", timestamp=2)
        await bridge.set_state("speaking", timestamp=3, force=True)
        self.assertEqual(len(client.messages), 2)
        self.assertEqual(client.messages[0]["timestamp"], 1)
        self.assertEqual(client.messages[1]["timestamp"], 3)


if __name__ == "__main__":
    unittest.main()
