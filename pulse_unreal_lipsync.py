import asyncio
import math
import logging
import time
from aurora_unreal_bridge import UnrealAvatarBridge

logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')

async def main():
    bridge = UnrealAvatarBridge(port=8771)
    await bridge.start()
    print('AURORA_UNREAL_PULSE_READY ws://127.0.0.1:8771', flush=True)
    start = time.time()
    last_count = -1
    try:
        while time.time() - start < 1800:
            count = len(bridge.clients)
            if count != last_count:
                print(f'client_count={count}', flush=True)
                last_count = count
            # Send state even before clients connect; once connected, force speaking every loop.
            await bridge.set_state('speaking', force=True)
            # Slow, obvious jaw pulses: 0→1→0 roughly twice per second.
            phase = (math.sin((time.time() - start) * math.pi * 2.0) + 1.0) / 2.0
            amp = max(0.05, min(1.0, phase))
            await bridge.send_lipsync([amp, amp, amp, amp], 50)
            await asyncio.sleep(0.05)
        await bridge.set_state('idle', force=True)
        print('AURORA_UNREAL_PULSE_DONE', flush=True)
    finally:
        await bridge.stop()

if __name__ == '__main__':
    asyncio.run(main())
