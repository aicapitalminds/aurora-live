#pragma once

#include "CoreMinimal.h"
#include "AnimGraphNode_Base.h"
#include "AnimNode_AuroraFaceIdle.h"
#include "AnimGraphNode_AuroraFaceIdle.generated.h"

UCLASS()
class AURORARUNTIMEEDITOR_API UAnimGraphNode_AuroraFaceIdle : public UAnimGraphNode_Base
{
    GENERATED_BODY()

public:
    UPROPERTY(EditAnywhere, Category = Settings)
    FAnimNode_AuroraFaceIdle Node;

    // UEdGraphNode interface
    virtual FText GetNodeTitle(ENodeTitleType::Type TitleType) const override;
    virtual FText GetTooltipText() const override;
    virtual FLinearColor GetNodeTitleColor() const override;
    virtual FString GetNodeCategory() const override;
};
