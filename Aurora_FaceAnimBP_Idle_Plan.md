# Aurora Face AnimBP — Idle + Lipsync Coexistence Plan

Target asset: `/Game/Aurora/Animation/ABP_Aurora_FacePreviewLipSync`
Goal: reliable Georgy lipsync FIRST, then add idle life without ever fighting it.

---

## Golden rules (do not break)

- Do NOT assign `PrimaryAnimation` or `SecondaryAnimation` at runtime.
- Do NOT use `AS_Aurora_Audio_To_Face_Test` in the live path.
- Do NOT replace Georgy generator assignment.
- Do NOT have idle write any jaw/mouth/lip curve.
- Idle writes ONLY: blink, eye-look, brow curves.

---

## Architecture decision: idle goes AFTER Georgy

```
Base / preview pose
  -> Georgy Realistic MetaHuman Lip Sync node   (untouched, FIRST)
  -> Modify Curve  (idle: blink + eye + brow)    (NEW, AFTER Georgy)
  -> Output Pose
```

Reasoning:
- Lipsync and idle drive DIFFERENT curves, so they cannot collide if idle runs last.
- "Before Georgy" risks the node normalizing/resetting the curve stream and wiping idle.
- A separate post-process AnimBP is wrong: that slot already runs RigLogic
  (converts curves -> face bones). Leave it alone.

Curve ownership:
- Georgy owns: jaw, mouth, lips, cheeks (mouth-adjacent).
- Idle owns: CTRL_expressions_eyeBlinkL / eyeBlinkR,
  eyeLookLeftL/R, eyeLookRightL/R, eyeLookUp*, eyeLookDown*, brow curves.

---

## STEP 0 — Restore baseline (verify before touching anything)

1. Confirm controller restored from:
   `Saved/PackagedPlugins/AuroraRuntime_BuildTest3/Source/AuroraRuntime/Private/AuroraLiveController.cpp`
2. Open `ABP_Aurora_FacePreviewLipSync`. Confirm AnimGraph is just:
   Base pose -> Modify Curve (set all idle pins to 0 / disconnected) -> Georgy node -> Output.
3. Play in editor, run live lipsync. Confirm mouth moves reliably, multiple takes.
   DO NOT proceed until lipsync is reliable with ZERO idle active.

---

## STEP 1 — Move Modify Curve to AFTER Georgy

1. In AnimGraph, disconnect the existing Modify Curve.
2. Reconnect so flow is: Base -> Georgy -> Modify Curve -> Output.
3. Leave all Modify Curve pins at 0 for now.
4. Test lipsync again. Still reliable? Good — placement is now safe.

Modify Curve Apply Mode: use "Blend" (alpha 1) or just drive the pin value.
Because idle curves come into this node at ~0 (Georgy never sets them),
setting the value directly is clean.

---

## STEP 2 — Natural blinks (Event Graph)

Variables (float): AuroraBlinkValue, BlinkTimer, NextBlinkAt, BlinkPhase.
In Event Blueprint Update Animation (delta time = DeltaSeconds):

```
BlinkTimer += DeltaSeconds
if not blinking and BlinkTimer >= NextBlinkAt:
    start blink (BlinkPhase = 0), reset BlinkTimer = 0
    NextBlinkAt = RandomRange(2.0, 6.0)

if blinking:
    BlinkPhase += DeltaSeconds / 0.12          // ~120ms full blink
    // eased close-then-open: 0 -> 1 -> 0
    if BlinkPhase < 0.5:  AuroraBlinkValue = ease(BlinkPhase * 2)
    else:                 AuroraBlinkValue = ease((1 - BlinkPhase) * 2)
    if BlinkPhase >= 1.0: stop blinking, AuroraBlinkValue = 0
```

Wire AuroraBlinkValue into Modify Curve pins for eyeBlinkL AND eyeBlinkR.
ease() = a smoothstep or sine ease, NOT linear (linear is what looked glitchy).

---

## STEP 3 — Subtle eye darts / micro gaze

Variables: EyeTargetX, EyeTargetY, EyeCurrentX, EyeCurrentY, GazeTimer, NextGazeAt.

```
GazeTimer += DeltaSeconds
if GazeTimer >= NextGazeAt:
    EyeTargetX = RandomRange(-0.10, 0.10)   // keep tiny
    EyeTargetY = RandomRange(-0.06, 0.06)
    GazeTimer = 0
    NextGazeAt = RandomRange(1.5, 4.0)

// smooth, never snap:
EyeCurrentX = FInterpTo(EyeCurrentX, EyeTargetX, DeltaSeconds, 6.0)
EyeCurrentY = FInterpTo(EyeCurrentY, EyeTargetY, DeltaSeconds, 6.0)
```

Map EyeCurrentX>0 -> eyeLookRight curves, <0 -> eyeLookLeft curves (use abs).
Map EyeCurrentY similarly to eyeLookUp / eyeLookDown.
Keep magnitudes small — micro-darts read as "alive", big moves read as "creepy".

Optional: pause darts (hold center) while a blink is mid-phase for realism.

---

## STEP 4 — Brow micro-movement (optional, very subtle)

Drive AuroraBrowRaise with a slow low-amplitude sine (amplitude ~0.05)
plus occasional tiny random nudges. Wire to brow curves only. Keep it barely visible.

---

## STEP 5 — Head / breathing / body idle (SEPARATE from face)

This is body, not face — do it in the Body AnimBP / Control Rig, not here.
- Add a looping ADDITIVE idle animation (subtle spine/chest breathing + micro head sway),
  blended additive over the base pose.
- Or drive spine/head bones with a slow sine in the body post-process.
- Keep it fully isolated from the Face AnimBP so it can never affect lipsync.

---

## STEP 6 — Mood generator (only if proven safe)

Gate behind a test:
1. Enable Georgy MoodGenerator alone, run lipsync 5+ takes.
2. If lipsync stays reliable, keep mood as its own layer AFTER Georgy,
   writing only non-mouth curves.
3. If lipsync degrades at all, remove it. Idle blink/eye is enough.

---

## Verification checklist (run after each step)

- [ ] Lipsync triggers every take (test 5+ times).
- [ ] Mouth shapes look correct during speech.
- [ ] Blinks fire at random 2–6s, eased not snapped.
- [ ] Eye darts are tiny and smooth.
- [ ] Idle continues while idle (no speech) AND during speech without breaking mouth.
- [ ] No PrimaryAnimation/SecondaryAnimation assigned anywhere at runtime.

If lipsync breaks: revert the last step only. Each step is independent and reversible.

---

## ACTUAL GRAPH (read live via MCP, 2026-06-28) — supersedes the sketch above

Real AnimGraph pose flow (source -> output):
  SequencePlayer_0 (PrimaryAnimation)   \
  SequencePlayer_1 (SecondaryAnimation)  -> LayeredBoneBlend_0 \
                                                                -> BlendListByBool_1 (bIsAnimationPlaying) \
  LocalRefPose ------------------------------------------------/                                            \
  SequenceEvaluator_0 (Primary, scrub)   \                                                                   -> BlendListByBool_0
  SequenceEvaluator_2 (Secondary, scrub)  -> LayeredBoneBlend_1 -----------------------------------------/   (bIsScrubbing)
                                                                                                              -> ModifyCurve_3 -> Georgy LipSync -> Root
This is the stock MetaHuman face PREVIEW graph (play/scrub Primary/Secondary anims) with an Aurora ModifyCurve injected.

Key node refPaths (Blueprint: /Game/Aurora/Animation/ABP_Aurora_FacePreviewLipSync.ABP_Aurora_FacePreviewLipSync, graph :AnimGraph):
- Output/Root:        .AnimGraphNode_Root_0
- Georgy lipsync:     .AnimGraphNode_BlendRealisticMetaHumanLipSync_0  (SourcePose in <- ModifyCurve_3; LipSyncGenerator <- GetAuroraLipSyncGenerator)
- Idle ModifyCurve:   .AnimGraphNode_ModifyCurve_3  (SourcePose in <- BlendListByBool_0; Pose out -> Georgy)
    CurveValues pins (index_id): 1=AuroraBlinkValue, 2=AuroraBlinkValue, 3=AuroraEyeLookLeft, 4=AuroraEyeLookLeft, 5=AuroraEyeLookRight, 6=AuroraEyeLookRight; 7=Alpha(1.0)

### CORRECTED conclusions
- Idle injection point (ModifyCurve_3, BEFORE Georgy) is CORRECT and lipsync-safe because blink/eye curves are disjoint from Georgy's mouth curves. Do NOT restructure the AnimGraph.
- "Glitchy idle" + "feels human" is solved in the EventGraph by driving AuroraBlinkValue / AuroraEyeLookLeft / AuroraEyeLookRight with eased blinks + FInterpTo eye darts. Zero lipsync risk (EventGraph is a K2 graph -> use write_graph_dsl in ONE call, token-efficient).
- Lipsync mouth SMOOTHING is a SEPARATE, optional step: insert a new ModifyCurve in WeightedMovingAverage mode BETWEEN Georgy and Root, listing mouth/jaw curves. Slightly higher risk (sits in lipsync path). Do after idle.
- AnimGraph anim-nodes are NOT serialized by read_graph_dsl (returns ""); use find_nodes + get_connected_subgraph + create_node/connect_pins for AnimGraph edits.

### Recommended order (revised)
1. EventGraph: smooth idle (blink + eye dart) driving existing variables. Lipsync-safe.
2. Verify lipsync + idle in editor.
3. (Optional) Lipsync mouth smoothing node between Georgy and Root.
