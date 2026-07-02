#pragma once

#include "CoreMinimal.h"
#include "GameFramework/Actor.h"
#include "AuroraAvatarBridgeComponent.h"
#include "AuroraLiveController.generated.h"

class USkeletalMeshComponent;
class UAnimInstance;
class URealisticMetaHumanLipSyncGenerator;
struct FAnimNode_ModifyCurve;

UCLASS(BlueprintType, Blueprintable)
class AURORARUNTIME_API AAuroraLiveController : public AActor
{
    GENERATED_BODY()

public:
    AAuroraLiveController();

    virtual void Tick(float DeltaSeconds) override;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Aurora|Bridge")
    TObjectPtr<UAuroraAvatarBridgeComponent> AvatarBridge;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    EAuroraAvatarState CurrentState = EAuroraAvatarState::Idle;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    FString CurrentStateString = TEXT("idle");

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    FString PreviousStateString = TEXT("idle");

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    FString LastEventType;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|State")
    FString LastPayloadJson;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|Face")
    float MouthOpen = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Aurora|LipSync")
    TObjectPtr<URealisticMetaHumanLipSyncGenerator> RealisticLipSyncGenerator;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|LipSync")
    int32 LastPcmSampleRate = 0;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|LipSync")
    int32 LastPcmChannels = 0;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|LipSync")
    int32 LastPcmSampleCount = 0;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|LipSync")
    int32 LastAssignedLipSyncAnimInstanceCount = 0;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|LipSync")
    int32 LastLipSyncPrewarmSampleCount = 0;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|LipSync")
    bool bLipSyncPrewarmed = false;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|Text")
    FString LastText;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face")
    TObjectPtr<AActor> TargetActor;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face")
    bool bAutoDiscoverTargetMeshes = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Motion")
    bool bEnableProceduralIdleMotion = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Motion", meta=(ClampMin="0.0", ClampMax="10.0"))
    float IdleBobAmplitude = 1.5f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Motion", meta=(ClampMin="0.0", ClampMax="10.0"))
    float IdleYawAmplitudeDegrees = 0.75f;

    // Breathing cycle speed in Hz (~0.22 = ~13 breaths/min, a calm resting rate).
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Motion", meta=(ClampMin="0.05", ClampMax="1.0"))
    float BreathingRateHz = 0.22f;

    // Peak forward lean (degrees) applied briefly when a gesture event arrives.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Motion", meta=(ClampMin="0.0", ClampMax="15.0"))
    float GestureLeanDegrees = 4.0f;

    // How long a single gesture impulse takes to decay back to rest (seconds).
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Motion", meta=(ClampMin="0.1", ClampMax="3.0"))
    float GestureDuration = 0.8f;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|Motion")
    float StateElapsedSeconds = 0.0f;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|Motion")
    float ProceduralMotionIntensity = 0.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face")
    TArray<FName> MouthOpenMorphTargetNames;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face")
    TArray<FName> MouthOpenCurveNames;

    // When false (default), the realistic NN lip sync (Face ABP) is the sole driver
    // of the mouth. Enable only as a crude fallback if the lip sync generator is
    // unavailable; it overrides nuanced visemes with a single jaw-open amplitude.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face")
    bool bApplyAmplitudeMouthFallback = false;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|Face")
    int32 LastAppliedMouthOpenCurveCount = 0;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|Face")
    int32 LastAppliedMouthOpenMorphCount = 0;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face|Idle")
    bool bEnableProceduralFacialIdle = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face|Idle", meta=(ClampMin="0.0", ClampMax="1.0"))
    float FacialIdleIntensity = 0.72f;

    // Baseline warm resting smile (mouthSmile + smiling eyes) kept on the face whenever
    // the mouth is free (not speaking), so her neutral reads as a vibrant co-host
    // rather than stern. 0 = fully neutral, ~0.18 = gentle, 0.4 = broad. Scaled by
    // FacialIdleIntensity and gently modulated so it never freezes.
    // PEAK of the slow smile-bloom cycle (she swells from ~neutral up to this, then relaxes back).
    // Bigger = bigger periodic smile. 0 disables the resting smile entirely.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face|Idle", meta=(ClampMin="0.0", ClampMax="1.0"))
    float IdleRestingSmile = 0.6f;

    // Fraction of the resting smile that persists WHILE speaking, blended under the NN
    // lip sync (mouth-corner raise + cheek raise only). Keeps her looking warm and
    // engaged as she talks without fighting the visemes. 0 = pristine lipsync / neutral
    // mouth during speech, 1 = full idle smile even mid-sentence. ~0.4 reads as a gentle
    // conversational smile.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face|Idle", meta=(ClampMin="0.0", ClampMax="1.0"))
    float SpeakingSmileScale = 0.4f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face|Idle", meta=(ClampMin="0.5", ClampMax="10.0"))
    float BlinkIntervalSeconds = 4.2f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face|Idle", meta=(ClampMin="0.02", ClampMax="0.5"))
    float BlinkDurationSeconds = 0.14f;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|Face|Idle")
    float ProceduralBlinkValue = 0.0f;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|Face|Idle")
    int32 LastAppliedFacialIdleMorphCount = 0;

    // Diagnostic: which anim instance/node property the facial idle writes to, whether the
    // previous tick's values survived until this tick (pre*), and what was just written (post*).
    UPROPERTY(BlueprintReadOnly, Category="Aurora|Face|Idle")
    FString FacialIdleDebug;

    // Spontaneous micro-expressions (grin, delight, wink, playful smirk, etc.) layered
    // on top of the continuous idle drift. Poses may include mouth/jaw (real smiles);
    // those channels are automatically suppressed while Speaking so the NN lip sync
    // stays the sole mouth driver, and play in full while idle/listening/thinking.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face|Idle")
    bool bEnableFacialMicroExpressions = true;

    // Randomized quiet gap between two spontaneous micro-expressions (seconds). Kept
    // short so a vibrant co-host is frequently doing something with her face.
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face|Idle", meta=(ClampMin="0.5", ClampMax="30.0"))
    float MicroExpressionIntervalMin = 1.0f;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face|Idle", meta=(ClampMin="0.5", ClampMax="60.0"))
    float MicroExpressionIntervalMax = 3.0f;

    // Peak strength of a micro-expression relative to its authored pose (0-1).
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Face|Idle", meta=(ClampMin="0.0", ClampMax="1.0"))
    float MicroExpressionIntensity = 1.0f;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|Face|Idle")
    FString ActiveMicroExpressionName;

    UPROPERTY(BlueprintReadOnly, Category="Aurora|Face|Idle")
    float ActiveMicroExpressionWeight = 0.0f;

    UPROPERTY(VisibleAnywhere, BlueprintReadOnly, Category="Aurora|Face")
    TArray<TObjectPtr<USkeletalMeshComponent>> TargetMeshComponents;

    UFUNCTION(BlueprintCallable, Category="Aurora|Face")
    void DiscoverTargetMeshes();

    UFUNCTION(BlueprintCallable, Category="Aurora|Face")
    void ApplyMouthOpenToMorphTargets(float NewMouthOpen);

    UFUNCTION(BlueprintCallable, Category="Aurora|Face|Idle")
    void ApplyProceduralFacialIdle(float DeltaSeconds);

    UFUNCTION(BlueprintCallable, Category="Aurora|LipSync")
    URealisticMetaHumanLipSyncGenerator* GetRealisticLipSyncGenerator() const { return RealisticLipSyncGenerator; }

    UFUNCTION(BlueprintCallable, Category="Aurora|LipSync")
    void ProcessAuroraPcmAudio(const TArray<float>& PcmData, int32 SampleRate, int32 Channels);

    UFUNCTION(BlueprintCallable, Category="Aurora|LipSync")
    void PrewarmLipSyncGenerator(int32 SampleRate = 24000, int32 Channels = 1, int32 DurationMs = 120);

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Camera")
    bool bAutoSetPlayerViewTarget = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Camera")
    TObjectPtr<AActor> PlayerViewTargetActor;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Camera")
    FString PlayerViewTargetActorLabel = TEXT("Aurora_View_Camera");

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Camera")
    bool bEnableKeyboardCameraZoom = true;

    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Camera")
    float CameraZoomSpeed = 220.0f;

    // When true, the view camera smoothly dollies in to frame the face while she is
    // Speaking and eases back to its authored idle pose otherwise. Owns the view
    // camera transform while enabled (keyboard zoom is suppressed in that mode).
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Camera|Framing")
    bool bEnableSpeakingCameraFraming = true;

    // Fraction of the base-camera -> face distance to close when fully framed
    // (0 = no move, 0.4 = dolly 40% of the way toward the face).
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Camera|Framing", meta=(ClampMin="0.0", ClampMax="0.9"))
    float CameraSpeakingPushIn = 0.4f;

    // How quickly the camera eases between idle and speaking framing (FInterpTo speed).
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Camera|Framing", meta=(ClampMin="0.1", ClampMax="10.0"))
    float CameraFramingBlendSpeed = 1.5f;

    // Fine vertical nudge (cm, at the character's own scale) above the resolved head
    // bone, lifting the aim from the head joint toward the eyes. The base aim point
    // is the head bone itself, so this stays correct at any scale (an absolute height
    // above the actor origin lands on the knees once the MetaHuman is scaled up).
    UPROPERTY(EditAnywhere, BlueprintReadWrite, Category="Aurora|Camera|Framing", meta=(ClampMin="0.0", ClampMax="80.0"))
    float CameraFocusHeight = 12.0f;

    // 0 = idle framing, 1 = fully pushed-in speaking framing. Read-only debug view.
    UPROPERTY(BlueprintReadOnly, Category="Aurora|Camera|Framing")
    float CameraFramingAlpha = 0.0f;

    UFUNCTION(BlueprintCallable, Category="Aurora|Camera")
    void ApplyPlayerViewTarget();

    UFUNCTION(BlueprintCallable, Category="Aurora|Bridge")
    void ConnectAurora();

    UFUNCTION(BlueprintCallable, Category="Aurora|Bridge")
    void DisconnectAurora();

    UFUNCTION(BlueprintImplementableEvent, Category="Aurora|State")
    void OnAuroraEnteredIdle();

    UFUNCTION(BlueprintImplementableEvent, Category="Aurora|State")
    void OnAuroraEnteredListening();

    UFUNCTION(BlueprintImplementableEvent, Category="Aurora|State")
    void OnAuroraEnteredThinking();

    UFUNCTION(BlueprintImplementableEvent, Category="Aurora|State")
    void OnAuroraEnteredSpeaking();

    UFUNCTION(BlueprintImplementableEvent, Category="Aurora|Face")
    void OnAuroraMouthOpenChanged(float NewMouthOpen);

    UFUNCTION(BlueprintImplementableEvent, Category="Aurora|Gesture")
    void OnAuroraGestureReceived(const FString& GestureName, float Intensity);

    UFUNCTION(BlueprintImplementableEvent, Category="Aurora|Text")
    void OnAuroraTextReceived(const FString& Text, bool bPartial);

protected:
    virtual void BeginPlay() override;
    virtual void EndPlay(const EEndPlayReason::Type EndPlayReason) override;

private:
    UFUNCTION()
    void HandleStateChanged(EAuroraAvatarState NewState, const FString& RawState);

    UFUNCTION()
    void HandleLipSync(float NewMouthOpen, const TArray<float>& WindowValues);

    UFUNCTION()
    void HandleText(const FString& Text, bool bPartial);

    UFUNCTION()
    void HandleGesture(const FString& GestureName, float Intensity);

    UFUNCTION()
    void HandleRawEvent(const FString& PayloadJson);

    void AssignLipSyncGeneratorToAnimInstances();
    void UpdateProceduralIdleMotion(float DeltaSeconds);
    void UpdateFacialMicroExpression(float DeltaSeconds);

    // Returns the face ABP's ModifyCurve anim node (the idle-expression injector), or null.
    static FAnimNode_ModifyCurve* FindFaceModifyCurveNode(UAnimInstance* AnimInstance);
    void UpdateCameraFraming(float DeltaSeconds);
    AActor* ResolveFramingCamera() const;

    TWeakObjectPtr<AActor> ProceduralMotionActor;
    FVector ProceduralBaseLocation = FVector::ZeroVector;
    FRotator ProceduralBaseRotation = FRotator::ZeroRotator;
    bool bHasProceduralBaseTransform = false;

    // Procedural facial idle runtime state (blink + eye darts).
    float IdleBlinkTimer = 2.0f;
    float IdleBlinkPhase = 0.0f;
    bool bIdleBlinkActive = false;
    float IdleGazeTimer = 1.0f;
    float IdleGazeLeft = 0.0f;
    float IdleGazeRight = 0.0f;
    float IdleGazeTargetLeft = 0.0f;
    float IdleGazeTargetRight = 0.0f;

    // Gesture impulse runtime state (drives a brief forward lean on the body).
    float GestureLeanAmount = 0.0f;
    float GestureTimer = 0.0f;

    // Spontaneous micro-expression runtime state. The pose table itself is a
    // file-local library in the .cpp; here we only track the active selection and
    // its ease-in/hold/ease-out envelope timing.
    int32 ActiveMicroExpressionIndex = INDEX_NONE;
    int32 LastMicroExpressionIndex = INDEX_NONE;
    float MicroExpressionTimer = 3.0f;
    float MicroExpressionElapsed = 0.0f;
    float MicroExpressionHold = 1.0f;

    // Speaking camera-framing runtime state. The idle base pose is captured once
    // from the live view camera; framing dollies in relative to it and eases back.
    TWeakObjectPtr<AActor> CameraFramingActor;
    bool bHasCameraBaseTransform = false;
    FVector CameraIdleBaseLocation = FVector::ZeroVector;
    FRotator CameraIdleBaseRotation = FRotator::ZeroRotator;
};
