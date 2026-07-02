#include "AnimGraphNode_AuroraFaceIdle.h"

FText UAnimGraphNode_AuroraFaceIdle::GetNodeTitle(ENodeTitleType::Type TitleType) const
{
    return NSLOCTEXT("Aurora", "AuroraFaceIdleTitle", "Aurora Face Idle");
}

FText UAnimGraphNode_AuroraFaceIdle::GetTooltipText() const
{
    return NSLOCTEXT("Aurora", "AuroraFaceIdleTooltip",
        "Applies Aurora's procedural facial idle curves (resting smile, brow drift, micro-expressions) "
        "published by AAuroraLiveController. Place last before Output, after the lip sync blend node.");
}

FLinearColor UAnimGraphNode_AuroraFaceIdle::GetNodeTitleColor() const
{
    return FLinearColor(0.85f, 0.35f, 0.65f);
}

FString UAnimGraphNode_AuroraFaceIdle::GetNodeCategory() const
{
    return TEXT("Aurora");
}
