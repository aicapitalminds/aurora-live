import asyncio
import json
import pathlib

import websockets
from aurora_unreal_bridge import UnrealAvatarBridge

async def main():
    bridge = UnrealAvatarBridge(port=8771)
    await bridge.start()
    try:
        async with websockets.connect('ws://127.0.0.1:8771') as ws:
            initial = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            await bridge.set_state('speaking', force=True, timestamp=10)
            state = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            await bridge.send_lipsync([0.0, 0.5, 1.2], 50, timestamp=11)
            lipsync = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
            result = {
                'initial': initial,
                'state': state,
                'lipsync': lipsync,
                'client_count_during_test': len(bridge.clients),
            }
    finally:
        await bridge.stop()
    pathlib.Path(r'C:/Users/AI/Documents/AuroraMigration/AURORA_UNREAL_WS_SMOKE_RESULT.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result, indent=2))

asyncio.run(main())
