# Aurora — Gaming Co-Host Roadmap

North star: Aurora is a UE 5.8 MetaHuman AI gaming co-host, streamed to Twitch.
Voice = Gemini Live API over websocket (stable). Visuals = UE 5.8 MetaHuman via MCP.

## Phase status

- [x] UE 5.8 project running, MetaHuman imported
- [x] Georgy Runtime MetaHuman Lip Sync working
- [x] Stable audio from Gemini Live websocket
- [ ] PHASE 1 (NOW): Believable face — smooth lipsync + idle life
- [ ] PHASE 2: Stream-ready presentation (framing, lighting, OBS/Twitch pipeline)
- [ ] PHASE 3: Expression & reactivity (mood/emotion tied to conversation)
- [ ] PHASE 4: Body presence (gestures, breathing, posture idle)
- [ ] PHASE 5: Environment — gaming room, move around, interact with objects

---

## PHASE 1 — Believable face (current)

Two independent levers:

### A. Smoothness of the lipsync (anti-jitter)
1. Add `Modify Curve` in WeightedMovingAverage mode AFTER Georgy, on mouth/jaw curves. Start light.
2. Keep mouth-smoothing separate from eye/idle curves so they don't interact.
3. Tune averaging window: too high = mushy/laggy mouth, too low = jitter remains.

### B. Idle life (see Aurora_FaceAnimBP_Idle_Plan.md)
- Random blinks 2-6s, eased not linear.
- Tiny smooth eye darts (FInterpTo, small magnitude).
- Subtle brow drift; face never 100% still.
- Idle ONLY on blink/eye/brow curves, applied AFTER Georgy node.

### Anti-uncanny rules
- Blink during gaze shifts (couple them).
- Slight L/R blink asymmetry.
- Always a faint background drift (breath/brow) so it never freezes.

Exit criteria: lipsync reliable across many takes AND face reads as alive at rest.

---

## PHASE 2 — Stream-ready (later)

- Camera framing + lighting that flatters the MetaHuman.
- Capture path into OBS, push to Twitch.
- Latency budget check: Gemini voice -> lipsync -> render -> stream.

## PHASE 3 — Expression & reactivity (later)

- Map conversation tone/emotion to facial expression layer (after Georgy, non-mouth curves).
- Gate any Georgy MoodGenerator behind a lipsync-stability test before adopting.

## PHASE 4 — Body presence (later)

- Additive breathing + micro head sway in BODY AnimBP (isolated from face).
- Conversational gestures.

## PHASE 5 — Environment (later)

- Gaming room scene; navigation; interact with objects/environment.

---

## Hard constraints (carry forward every phase)

- Never assign PrimaryAnimation/SecondaryAnimation at runtime.
- Never use AS_Aurora_Audio_To_Face_Test in live path.
- Never replace Georgy generator assignment.
- New layers go AFTER the Georgy node, on curves it doesn't drive.
- Build in small reversible steps (user is token/budget limited).

Project path: C:/Users/AI/Documents/Unreal Projects/AuroraMetaHuman 5.8
Face AnimBP: /Game/Aurora/Animation/ABP_Aurora_FacePreviewLipSync
