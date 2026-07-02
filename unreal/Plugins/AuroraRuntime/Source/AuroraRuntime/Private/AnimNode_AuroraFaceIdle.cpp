#include "AnimNode_AuroraFaceIdle.h"
#include "AuroraFaceIdleChannel.h"
#include "Animation/AnimCurveTypes.h"

namespace
{
    // Every RigLogic raw control this node may ever drive. All of them are written every
    // evaluation (0 when the idle system is quiet) so the curve NAMES exist in the output
    // stream from the very first frame: downstream consumers (ABP_Face_PostProcess /
    // RigLogic) resolve their input curve set at initialization, and names that first
    // appear later are ignored — that is why compile-time baked curve values rendered
    // while identical values set at runtime did not.
    const FName GAuroraFaceIdleChannels[] =
    {
        TEXT("CTRL_expressions_browRaiseInL"),    TEXT("CTRL_expressions_browRaiseInR"),
        TEXT("CTRL_expressions_browRaiseOuterL"), TEXT("CTRL_expressions_browRaiseOuterR"),
        TEXT("CTRL_expressions_browLateralL"),    TEXT("CTRL_expressions_browLateralR"),
        TEXT("CTRL_expressions_eyeSquintInnerL"), TEXT("CTRL_expressions_eyeSquintInnerR"),
        TEXT("CTRL_expressions_eyeCheekRaiseL"),  TEXT("CTRL_expressions_eyeCheekRaiseR"),
        TEXT("CTRL_expressions_eyeWidenL"),       TEXT("CTRL_expressions_eyeWidenR"),
        TEXT("CTRL_expressions_eyeBlinkL"),
        // eyeBlinkR is intentionally NOT in this list: it reaches the face through the
        // published-curves loop in Evaluate (the graph already writes the name every
        // frame). Growing this static array breaks Live Coding (global data layout).
        TEXT("CTRL_expressions_noseWrinkleL"),    TEXT("CTRL_expressions_noseWrinkleR"),
        TEXT("CTRL_expressions_mouthCornerPullL"), TEXT("CTRL_expressions_mouthCornerPullR"),
        TEXT("CTRL_expressions_mouthDimpleL"),    TEXT("CTRL_expressions_mouthDimpleR"),
        TEXT("CTRL_expressions_jawOpen"),
    };
}

void FAnimNode_AuroraFaceIdle::Initialize_AnyThread(const FAnimationInitializeContext& Context)
{
    Super::Initialize_AnyThread(Context);
    SourcePose.Initialize(Context);
}

void FAnimNode_AuroraFaceIdle::CacheBones_AnyThread(const FAnimationCacheBonesContext& Context)
{
    Super::CacheBones_AnyThread(Context);
    SourcePose.CacheBones(Context);
}

void FAnimNode_AuroraFaceIdle::Update_AnyThread(const FAnimationUpdateContext& Context)
{
    SourcePose.Update(Context);
    FAuroraFaceIdleChannel::Consume(CurrentCurves);
}

void FAnimNode_AuroraFaceIdle::Evaluate_AnyThread(FPoseContext& Output)
{
    SourcePose.Evaluate(Output);

    for (const FName& Channel : GAuroraFaceIdleChannels)
    {
        // Additive on top of whatever the graph produced (lipsync etc.); clamped to the
        // rig's 0..1 control range so stacked drift + micro-expressions can't overdrive.
        // Negative published values deliberately SUPPRESS an upstream curve (the clamp
        // floors the result at 0) — used to hold the off eye open during a wink.
        // Channels the idle system isn't currently driving are still written (as +0) so
        // the curve names exist in the stream from the first frame — see note above.
        const float* IdleValue = CurrentCurves.Find(Channel);
        const float Existing = Output.Curve.Get(Channel);
        Output.Curve.Set(Channel, FMath::Clamp(Existing + (IdleValue ? *IdleValue : 0.0f), 0.0f, 1.0f));
    }

    // Also apply any published curve that is not in the fixed list. Live Coding cannot
    // re-initialize the file-static channel array, so a channel added between full
    // rebuilds only reaches the face through this loop; it only works for names the
    // graph already writes every frame (RigLogic ignores names that first appear late).
    for (const TPair<FName, float>& Pair : CurrentCurves)
    {
        bool bInFixedList = false;
        for (const FName& Channel : GAuroraFaceIdleChannels)
        {
            if (Channel == Pair.Key)
            {
                bInFixedList = true;
                break;
            }
        }
        if (!bInFixedList)
        {
            const float Existing = Output.Curve.Get(Pair.Key);
            Output.Curve.Set(Pair.Key, FMath::Clamp(Existing + Pair.Value, 0.0f, 1.0f));
        }
    }
}

void FAnimNode_AuroraFaceIdle::GatherDebugData(FNodeDebugData& DebugData)
{
    DebugData.AddDebugItem(FString::Printf(TEXT("AuroraFaceIdle (%d curves)"), CurrentCurves.Num()));
    SourcePose.GatherDebugData(DebugData.BranchFlow(1.0f));
}
