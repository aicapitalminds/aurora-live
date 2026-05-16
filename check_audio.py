import sounddevice as sd

print("=== Available Audio Devices ===")
devices = sd.query_devices()
for i, dev in enumerate(devices):
    if dev['max_output_channels'] > 0:
        print(f"[{i}] {dev['name']} (Out: {dev['max_output_channels']})")

print("\n=== Recommended Output ===")
for i, dev in enumerate(devices):
    if "VoiceMeeter Input".lower() in dev['name'].lower() or "VoiceMeeter VAIO".lower() in dev['name'].lower():
        print(f"✅ Use this exact string in aurora-live.py: \"{dev['name']}\"")
        break
else:
    print("❌ VoiceMeeter not found yet. Make sure it's installed and running!")
