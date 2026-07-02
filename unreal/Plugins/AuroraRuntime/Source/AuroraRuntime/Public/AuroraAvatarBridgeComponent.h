#pragma once

#include "CoreMinimal.h"
#include "Components/ActorComponent.h"
#include "IWebSocket.h"
#include "AuroraAvatarBridgeComponent.generated.h"

UENUM(BlueprintType)
enum class EAuroraAvatarState : uint8
{
    Idle UMETA(DisplayName = "Idle"),
    Listening UMETA(DisplayName = "Listening"),
    Thinking UMETA(DisplayName = "Thinking"),
    Speaking UMETA(DisplayName = "Speaking")
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FAuroraStateChangedSignature, EAuroraAvatarState, NewState, const FString&, RawState);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FAuroraLipSyncSignature, float, MouthOpen, const TArray<float>&, WindowValues);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FAuroraTextSignature, const FString&, Text, bool, bPartial);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FAuroraGestureSignature, const FString&, GestureName, float, Intensity);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FAuroraRawEventSignature, const FString&, PayloadJson);
DECLARE_DYNAMIC_MULTICAST_DELEGATE_OneParam(FAuroraConnectionSignature, bool, bConnected);

UCLASS(ClassGroup=(Aurora), meta=(BlueprintSpawnableComponent))
class AURORARUNTIME_API UAuroraAvatarBridgeComponent : public UActorComponent
{
    GENERATED_BODY()

public:
    UAuroraAvatarBridgeComponent();

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Bridge")
    FString BridgeUrl = TEXT("ws://127.0.0.1:8771");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Bridge")
    bool bAutoConnect = true;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    bool bConnected = false;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    EAuroraAvatarState CurrentState = EAuroraAvatarState::Idle;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    FString CurrentStateString = TEXT("idle");

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    FString LastEventType;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    FString LastPayloadJson;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    float MouthOpen = 0.0f;

    UPROPERTY(BlueprintAssignable, Category="Aurora|Events")
    FAuroraConnectionSignature OnAuroraConnectionChanged;

    UPROPERTY(BlueprintAssignable, Category="Aurora|Events")
    FAuroraStateChangedSignature OnAuroraStateChanged;

    UPROPERTY(BlueprintAssignable, Category="Aurora|Events")
    FAuroraLipSyncSignature OnAuroraLipSync;

    UPROPERTY(BlueprintAssignable, Category="Aurora|Events")
    FAuroraTextSignature OnAuroraText;

    UPROPERTY(BlueprintAssignable, Category="Aurora|Events")
    FAuroraGestureSignature OnAuroraGesture;

    UPROPERTY(BlueprintAssignable, Category="Aurora|Events")
    FAuroraRawEventSignature OnAuroraRawEvent;

    UFUNCTION(BlueprintCallable, Category="Aurora|Bridge")
    void Connect();

    UFUNCTION(BlueprintCallable, Category="Aurora|Bridge")
    void Disconnect();

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    TSharedPtr<IWebSocket> Socket;

    void HandleConnected();
    void HandleConnectionError(const FString& Error);
    void HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean);
    void HandleMessage(const FString& Message);
    void ApplyStateString(const FString& StateString);
};
