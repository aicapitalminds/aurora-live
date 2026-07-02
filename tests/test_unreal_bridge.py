import asyncio
import json
import unittest

from aurora_unreal_bridge import (
    AuroraAvatarState,
    UnrealAvatarBridge,
    build_audio_pcm_event,
    build_lipsync_event,
    build_lipsync_prewarm_event,
    build_state_event,
    build_world_action_event,
    build_world_action_result_event,
    build_world_context_event,
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

    def test_audio_pcm_event_schema_encodes_audio_for_future_plugin_path(self):
        event = build_audio_pcm_event(
            b"\x00\x01\x02\x03",
            sample_rate=16000,
            channels=1,
            sample_format="int16",
            sequence=7,
            timestamp=10,
        )
        self.assertEqual(event["type"], "avatar.audio.pcm")
        self.assertEqual(event["sampleRate"], 16000)
        self.assertEqual(event["channels"], 1)
        self.assertEqual(event["format"], "int16")
        self.assertEqual(event["seq"], 7)
        self.assertEqual(event["byteLength"], 4)
        self.assertEqual(event["audioBase64"], "AAECAw==")
        self.assertEqual(event["timestamp"], 10)

    def test_audio_pcm_event_rejects_invalid_format(self):
        with self.assertRaises(ValueError):
            build_audio_pcm_event(b"\x00", sample_rate=16000, sample_format="mp3")

    def test_lipsync_prewarm_event_schema(self):
        event = build_lipsync_prewarm_event(sample_rate=24000, channels=1, duration_ms=120, timestamp=11)
        self.assertEqual(event["type"], "avatar.lipsync.prewarm")
        self.assertEqual(event["sampleRate"], 24000)
        self.assertEqual(event["channels"], 1)
        self.assertEqual(event["durationMs"], 120)
        self.assertEqual(event["timestamp"], 11)

    async def test_send_lipsync_prewarm_broadcasts_schema(self):
        bridge = UnrealAvatarBridge()
        client = FakeClient()
        bridge.clients.add(client)
        await bridge.send_lipsync_prewarm(sample_rate=24000, channels=1, duration_ms=80, timestamp=12)
        self.assertEqual(client.messages[0]["type"], "avatar.lipsync.prewarm")
        self.assertEqual(client.messages[0]["durationMs"], 80)

    async def test_send_audio_pcm_broadcasts_schema(self):
        bridge = UnrealAvatarBridge()
        client = FakeClient()
        bridge.clients.add(client)
        await bridge.send_audio_pcm(b"\x00\x00", sample_rate=16000, sample_format="int16", sequence=1)
        self.assertEqual(client.messages[0]["type"], "avatar.audio.pcm")
        self.assertEqual(client.messages[0]["sampleRate"], 16000)
        self.assertEqual(client.messages[0]["audioBase64"], "AAA=")

    def test_world_context_event_schema(self):
        event = build_world_context_event(
            {"location": [0, 0, 0], "state": "idle"},
            [{"id": "chair_01", "tags": ["sit_target"], "distance": 120}],
            scene="test_room",
            timestamp=42,
        )
        self.assertEqual(event["type"], "world.context")
        self.assertEqual(event["scene"], "test_room")
        self.assertEqual(event["nearby"][0]["id"], "chair_01")
        self.assertEqual(event["timestamp"], 42)

    def test_world_action_event_schema(self):
        event = build_world_action_event("look_at", target="mug_01", params={"duration": 2}, request_id="req-1", timestamp=43)
        self.assertEqual(event["type"], "world.action")
        self.assertEqual(event["action"], "look_at")
        self.assertEqual(event["target"], "mug_01")
        self.assertEqual(event["params"], {"duration": 2})
        self.assertEqual(event["requestId"], "req-1")

    def test_world_action_result_schema(self):
        event = build_world_action_result_event("req-1", ok=True, action="look_at", message="done", data={"actor": "mug_01"}, timestamp=44)
        self.assertEqual(event["type"], "world.action.result")
        self.assertTrue(event["ok"])
        self.assertEqual(event["requestId"], "req-1")
        self.assertEqual(event["data"], {"actor": "mug_01"})

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
