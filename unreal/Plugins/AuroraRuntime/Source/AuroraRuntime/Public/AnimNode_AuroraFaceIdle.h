#pragma once

#include "CoreMinimal.h"
#include "Animation/AnimNodeBase.h"
#include "AnimNode_AuroraFaceIdle.generated.h"

// Applies Aurora's procedural facial-idle curves (published by AAuroraLiveController via
// FAuroraFaceIdleChannel) onto the pose's curve set. Place LAST before Output in
// ABP_Aurora_Face — downstream of BlendRealisticMetaHumanLipSync, which overwrites every
// raw face curve it knows about each frame and would crush anything injected earlier.
// Curve names must be RigLogic RAW controls (CTRL_expressions_mouthCornerPullL etc.);
// the final output curves feed ABP_Face_PostProcess's RigLogic, which drives the face.
USTRUCT(BlueprintInternalUseOnly)
struct AURORARUNTIME_API FAnimNode_AuroraFaceIdle : public FAnimNode_Base
{
    GENERATED_BODY()

    UPROPERTY(EditAnywhere, EditFixedSize, BlueprintReadWrite, Category = Links)
    FPoseLink SourcePose;

    // FAnimNode_Base interface
    virtual void Initialize_AnyThread(const FAnimationInitializeContext& Context) override;
    virtual void CacheBones_AnyThread(const FAnimationCacheBonesContext& Context) override;
    virtual void Update_AnyThread(const FAnimationUpdateContext& Context) override;
    virtual void Evaluate_AnyThread(FPoseContext& Output) override;
    virtual void GatherDebugData(FNodeDebugData& DebugData) override;

private:
    // Snapshot taken during Update, applied during Evaluate (both on the anim thread).
    TMap<FName, float> CurrentCurves;
};
