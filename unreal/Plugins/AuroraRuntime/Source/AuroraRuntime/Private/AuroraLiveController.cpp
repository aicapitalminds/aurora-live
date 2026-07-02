#include "AuroraLiveController.h"

#include "Components/SceneComponent.h"
#include "Dom/JsonObject.h"
#include "Misc/Base64.h"
#include "RealisticMetaHumanLipSyncGenerator.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "UObject/UnrealType.h"
#include "Components/SkeletalMeshComponent.h"
#include "Animation/AnimInstance.h"
#include "Animation/AnimClassInterface.h"
#include "AnimNodes/AnimNode_ModifyCurve.h"
#include "AuroraFaceIdleChannel.h"
#include "EngineUtils.h"
#include "GameFramework/PlayerController.h"
#include "InputCoreTypes.h"
#include "Kismet/KismetMathLibrary.h"
#include "TimerManager.h"

AAuroraLiveController::AAuroraLiveController()
{
    PrimaryActorTick.bCanEverTick = true;
    PrimaryActorTick.TickGroup = TG_PostUpdateWork;

    USceneComponent* SceneRoot = CreateDefaultSubobject<USceneComponent>(TEXT("SceneRoot"));
    RootComponent = SceneRoot;

    AvatarBridge = CreateDefaultSubobject<UAuroraAvatarBridgeComponent>(TEXT("AuroraAvatarBridge"));

    MouthOpenMorphTargetNames = {
        TEXT("jawOpen"),
        TEXT("mouthOpen"),
        TEXT("MouthOpen"),
        TEXT("CTRL_C_jawOpen"),
        TEXT("CTRL_C_mouthOpen")
    };

    MouthOpenCurveNames = {
        // UE 5.8 MetaHuman Face_Archetype_Skeleton exposes high-level CTRL_expressions curves
        // plus ARKit-compatible aliases. These are better live-input targets than final head_lod mesh outputs.
        TEXT("CTRL_expressions_jawOpen"),
        TEXT("CTRL_expressions_jawOpenExtreme"),
        TEXT("CTRL_expressions_mouthLowerLipDepressL"),
        TEXT("CTRL_expressions_mouthLowerLipDepressR"),
        TEXT("CTRL_expressions_mouthUpperLipRaiseL"),
        TEXT("CTRL_expressions_mouthUpperLipRaiseR"),
        TEXT("CTRL_expressions_mouthStretchL"),
        TEXT("CTRL_expressions_mouthStretchR"),
        TEXT("JawOpen"),
        TEXT("MouthLowerDownLeft"),
        TEXT("MouthLowerDownRight"),
        TEXT("MouthFunnel"),
        TEXT("head_lod0_mesh__jaw_open")
    };
}

void AAuroraLiveController::Tick(float DeltaSeconds)
{
    Super::Tick(DeltaSeconds);

    // The realistic NN lip sync (Face ABP) is the source of truth for the mouth.
    // Only apply the crude single-amplitude override as an explicit fallback so it
    // doesn't fight the nuanced visemes produced by the lip sync generator.
    if (bApplyAmplitudeMouthFallback && MouthOpen > 0.001f)
    {
        ApplyMouthOpenToMorphTargets(MouthOpen);
    }

    if (RealisticLipSyncGenerator && LastAssignedLipSyncAnimInstanceCount == 0)
    {
        AssignLipSyncGeneratorToAnimInstances();
    }

    // Subtle "aliveness" layers: whole-body breathing/sway/weight-shift, and
    // micro facial motion on top of the ABP's blink + gaze.
    UpdateProceduralIdleMotion(DeltaSeconds);
    ApplyProceduralFacialIdle(DeltaSeconds);

    if (bEnableKeyboardCameraZoom && PlayerViewTargetActor && !bEnableSpeakingCameraFraming)
    {
        float Direction = 0.0f;
        APlayerController* PC = GetWorld() ? GetWorld()->GetFirstPlayerController() : nullptr;
        if (PC)
        {
            if (PC->IsInputKeyDown(EKeys::Equals) || PC->IsInputKeyDown(EKeys::Add) || PC->IsInputKeyDown(EKeys::MouseScrollUp))
            {
                Direction += 1.0f;
            }
            if (PC->IsInputKeyDown(EKeys::Hyphen) || PC->IsInputKeyDown(EKeys::Subtract) || PC->IsInputKeyDown(EKeys::MouseScrollDown))
            {
                Direction -= 1.0f;
            }
        }

        if (!FMath::IsNearlyZero(Direction))
        {
            AActor* CameraActor = PlayerViewTargetActor.Get();
            const FVector CameraLocation = CameraActor->GetActorLocation();
            const FVector TargetLocation = TargetActor ? TargetActor->GetActorLocation() + FVector(0, 0, 120) : FVector::ZeroVector;
            const FVector ToTarget = (TargetLocation - CameraLocation).GetSafeNormal();
            CameraActor->SetActorLocation(CameraLocation + ToTarget * Direction * CameraZoomSpeed * DeltaSeconds);
            CameraActor->SetActorRotation(UKismetMathLibrary::FindLookAtRotation(CameraActor->GetActorLocation(), TargetLocation));
        }
    }

    // Automatic close-up framing: push in on the face while Speaking, ease back otherwise.
    UpdateCameraFraming(DeltaSeconds);
}

void AAuroraLiveController::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    // The face-idle channel is static; clear it so a stale expression doesn't leak into
    // the next PIE session or linger after the controller is destroyed.
    FAuroraFaceIdleChannel::Publish(TMap<FName, float>());
    Super::EndPlay(EndPlayReason);
}

void AAuroraLiveController::BeginPlay()
{
    Super::BeginPlay();

    if (!RealisticLipSyncGenerator)
    {
        FRealisticMetaHumanLipSyncConfig LipSyncConfig;
        LipSyncConfig.ModelType = ERealisticMetaHumanLipSyncModelType::HighlyOptimized;
        RealisticLipSyncGenerator = URealisticMetaHumanLipSyncGenerator::CreateRealisticMetaHumanLipSyncGenerator(LipSyncConfig);
        if (RealisticLipSyncGenerator)
        {
            UE_LOG(LogTemp, Log, TEXT("AuroraLiveController created Realistic MetaHuman Lip Sync generator"));
        }
        else
        {
            UE_LOG(LogTemp, Warning, TEXT("AuroraLiveController failed to create Realistic MetaHuman Lip Sync generator"));
        }
    }

    if (bAutoDiscoverTargetMeshes)
    {
        DiscoverTargetMeshes();
    }
    AssignLipSyncGeneratorToAnimInstances();

    if (bAutoSetPlayerViewTarget && GetWorld())
    {
        FTimerHandle ViewTargetTimerHandle;
        GetWorld()->GetTimerManager().SetTimer(
            ViewTargetTimerHandle,
            this,
            &AAuroraLiveController::ApplyPlayerViewTarget,
            0.25f,
            false);
    }

    if (AvatarBridge)
    {
        AvatarBridge->OnAuroraStateChanged.AddDynamic(this, &AAuroraLiveController::HandleStateChanged);
        AvatarBridge->OnAuroraLipSync.AddDynamic(this, &AAuroraLiveController::HandleLipSync);
        AvatarBridge->OnAuroraText.AddDynamic(this, &AAuroraLiveController::HandleText);
        AvatarBridge->OnAuroraGesture.AddDynamic(this, &AAuroraLiveController::HandleGesture);
        AvatarBridge->OnAuroraRawEvent.AddDynamic(this, &AAuroraLiveController::HandleRawEvent);
    }
}

void AAuroraLiveController::ConnectAurora()
{
    if (AvatarBridge)
    {
        AvatarBridge->Connect();
    }
}

void AAuroraLiveController::ApplyPlayerViewTarget()
{
    if (!GetWorld())
    {
        return;
    }

    AActor* ViewTarget = PlayerViewTargetActor.Get();
    if (!ViewTarget && !PlayerViewTargetActorLabel.IsEmpty())
    {
        for (TActorIterator<AActor> It(GetWorld()); It; ++It)
        {
            AActor* Actor = *It;
            const FName DesiredTag(*PlayerViewTargetActorLabel);
            if (IsValid(Actor) && (Actor->ActorHasTag(DesiredTag) || Actor->GetName().Contains(PlayerViewTargetActorLabel)))
            {
                ViewTarget = Actor;
                break;
            }
        }
    }

    if (!ViewTarget)
    {
        UE_LOG(LogTemp, Warning, TEXT("AuroraLiveController could not find player view target '%s'"), *PlayerViewTargetActorLabel);
        return;
    }

    APlayerController* PlayerController = GetWorld()->GetFirstPlayerController();
    if (!PlayerController)
    {
        UE_LOG(LogTemp, Warning, TEXT("AuroraLiveController could not find PlayerController for view target '%s'"), *ViewTarget->GetName());
        return;
    }

    PlayerController->SetViewTarget(ViewTarget);
    UE_LOG(LogTemp, Log, TEXT("AuroraLiveController set Player 0 view target to %s"), *ViewTarget->GetName());
}

AActor* AAuroraLiveController::ResolveFramingCamera() const
{
    // Prefer an explicitly assigned view camera; otherwise drive whatever the
    // player is actually looking through (this level activates the camera via
    // auto-activate, so PlayerViewTargetActor is left unset).
    if (PlayerViewTargetActor)
    {
        return PlayerViewTargetActor.Get();
    }
    if (UWorld* World = GetWorld())
    {
        if (APlayerController* PC = World->GetFirstPlayerController())
        {
            return PC->GetViewTarget();
        }
    }
    return nullptr;
}

void AAuroraLiveController::UpdateCameraFraming(float DeltaSeconds)
{
    if (!bEnableSpeakingCameraFraming)
    {
        // Hand the camera back to manual/authored control and forget the base so a
        // fresh idle pose is captured if framing is toggled on again.
        bHasCameraBaseTransform = false;
        CameraFramingAlpha = 0.0f;
        return;
    }

    AActor* Camera = ResolveFramingCamera();
    if (!IsValid(Camera))
    {
        return;
    }

    // Resolve the face/aim point from the same actor the idle motion drives.
    AActor* FaceActor = TargetActor ? TargetActor.Get() : nullptr;
    if (!FaceActor && TargetMeshComponents.Num() > 0 && IsValid(TargetMeshComponents[0]))
    {
        FaceActor = TargetMeshComponents[0]->GetOwner();
    }
    if (!FaceActor || Camera == FaceActor || Camera == this)
    {
        return;
    }

    // Capture the authored idle pose once (re-capture if the camera changes).
    if (!bHasCameraBaseTransform || CameraFramingActor.Get() != Camera)
    {
        CameraIdleBaseLocation = Camera->GetActorLocation();
        CameraIdleBaseRotation = Camera->GetActorRotation();
        CameraFramingActor = Camera;
        bHasCameraBaseTransform = true;
    }

    // Ease toward the pushed-in framing while Speaking, back to idle otherwise.
    const float TargetAlpha = (CurrentState == EAuroraAvatarState::Speaking) ? 1.0f : 0.0f;
    CameraFramingAlpha = FMath::FInterpTo(CameraFramingAlpha, TargetAlpha, DeltaSeconds, CameraFramingBlendSpeed);

    // Essentially idle: snap exactly back to the authored pose and stop touching it.
    if (CameraFramingAlpha < KINDA_SMALL_NUMBER)
    {
        Camera->SetActorLocationAndRotation(CameraIdleBaseLocation, CameraIdleBaseRotation);
        return;
    }

    // Aim at the actual head bone so the framing stays correct at any character scale
    // (an absolute height above the actor origin lands on the knees once she is scaled
    // up). CameraFocusHeight is a small lift from the head joint toward the eyes, taken
    // at the character's own scale so it tracks the mesh.
    static const FName HeadBoneName(TEXT("head"));
    FVector HeadWorldLocation = FaceActor->GetActorLocation();
    float CharacterScaleZ = FaceActor->GetActorScale3D().Z;
    bool bResolvedHeadBone = false;
    for (USkeletalMeshComponent* Mesh : TargetMeshComponents)
    {
        if (IsValid(Mesh) && Mesh->GetBoneIndex(HeadBoneName) != INDEX_NONE)
        {
            HeadWorldLocation = Mesh->GetSocketLocation(HeadBoneName);
            CharacterScaleZ = Mesh->GetComponentScale().Z;
            bResolvedHeadBone = true;
            break;
        }
    }

    // Fallback if no head bone was found: approximate eye height at the character's
    // scale (nominal MetaHuman eyes sit ~160 cm above the feet at 1x).
    const FVector FocusPoint = bResolvedHeadBone
        ? HeadWorldLocation + FVector(0.0f, 0.0f, CameraFocusHeight * CharacterScaleZ)
        : HeadWorldLocation + FVector(0.0f, 0.0f, 160.0f * CharacterScaleZ);

    // Dolly a fraction of the way from the idle pose toward the face, scaled by alpha.
    const FVector PushedInLocation = FMath::Lerp(CameraIdleBaseLocation, FocusPoint, CameraSpeakingPushIn);
    const FVector FramedLocation = FMath::Lerp(CameraIdleBaseLocation, PushedInLocation, CameraFramingAlpha);

    // Keep the authored idle rotation at alpha 0; look straight at the face at alpha 1.
    const FRotator LookAtFace = UKismetMathLibrary::FindLookAtRotation(FramedLocation, FocusPoint);
    const FQuat FramedRotation = FQuat::Slerp(CameraIdleBaseRotation.Quaternion(), LookAtFace.Quaternion(), CameraFramingAlpha);

    Camera->SetActorLocationAndRotation(FramedLocation, FramedRotation);
}

void AAuroraLiveController::DisconnectAurora()
{
    if (AvatarBridge)
    {
        AvatarBridge->Disconnect();
    }
}

void AAuroraLiveController::DiscoverTargetMeshes()
{
    TargetMeshComponents.Reset();

    AActor* SearchActor = TargetActor ? TargetActor.Get() : GetOwner();
    if (!SearchActor)
    {
        SearchActor = this;
    }

    TArray<USkeletalMeshComponent*> Meshes;
    SearchActor->GetComponents<USkeletalMeshComponent>(Meshes, true);

    // If the controller was placed next to a spawned MetaHuman editor actor rather than attached to it,
    // search nearby actors as a practical fallback for test scenes.
    if (Meshes.Num() == 0 && GetWorld())
    {
        const FVector Origin = GetActorLocation();
        for (TActorIterator<AActor> It(GetWorld()); It; ++It)
        {
            AActor* Actor = *It;
            if (!Actor || Actor == this)
            {
                continue;
            }

            if (FVector::DistSquared(Actor->GetActorLocation(), Origin) > FMath::Square(1000.0f))
            {
                continue;
            }

            TArray<USkeletalMeshComponent*> ActorMeshes;
            Actor->GetComponents<USkeletalMeshComponent>(ActorMeshes, true);
            for (USkeletalMeshComponent* Mesh : ActorMeshes)
            {
                Meshes.AddUnique(Mesh);
            }
        }
    }

    for (USkeletalMeshComponent* Mesh : Meshes)
    {
        if (IsValid(Mesh))
        {
            TargetMeshComponents.Add(Mesh);
        }
    }
}

void AAuroraLiveController::ApplyMouthOpenToMorphTargets(float NewMouthOpen)
{
    const float ClampedValue = FMath::Clamp(NewMouthOpen, 0.0f, 1.0f);
    LastAppliedMouthOpenMorphCount = 0;
    LastAppliedMouthOpenCurveCount = 0;

    if (TargetMeshComponents.Num() == 0 && bAutoDiscoverTargetMeshes)
    {
        DiscoverTargetMeshes();
    }

    for (USkeletalMeshComponent* Mesh : TargetMeshComponents)
    {
        if (!IsValid(Mesh))
        {
            continue;
        }

        for (const FName& MorphTargetName : MouthOpenMorphTargetNames)
        {
            Mesh->SetMorphTarget(MorphTargetName, ClampedValue, false);
            ++LastAppliedMouthOpenMorphCount;
        }

        if (UAnimInstance* AnimInstance = Mesh->GetAnimInstance())
        {
            for (const FName& CurveName : MouthOpenCurveNames)
            {
                AnimInstance->OverrideCurveValue(CurveName, ClampedValue);
                ++LastAppliedMouthOpenCurveCount;
            }
        }
    }
}

void AAuroraLiveController::HandleStateChanged(EAuroraAvatarState NewState, const FString& RawState)
{
    PreviousStateString = CurrentStateString;
    CurrentState = NewState;
    CurrentStateString = RawState;
    LastEventType = TEXT("avatar.state");

    switch (NewState)
    {
    case EAuroraAvatarState::Listening:
        OnAuroraEnteredListening();
        break;
    case EAuroraAvatarState::Thinking:
        OnAuroraEnteredThinking();
        break;
    case EAuroraAvatarState::Speaking:
        OnAuroraEnteredSpeaking();
        break;
    case EAuroraAvatarState::Idle:
    default:
        OnAuroraEnteredIdle();
        break;
    }
}

void AAuroraLiveController::HandleLipSync(float NewMouthOpen, const TArray<float>& WindowValues)
{
    MouthOpen = FMath::Clamp(NewMouthOpen, 0.0f, 1.0f);
    LastEventType = TEXT("avatar.lipsync.amplitude");
    ApplyMouthOpenToMorphTargets(MouthOpen);
    OnAuroraMouthOpenChanged(MouthOpen);
}

void AAuroraLiveController::HandleText(const FString& Text, bool bPartial)
{
    LastText = Text;
    LastEventType = bPartial ? TEXT("avatar.text.partial") : TEXT("avatar.text.final");
    OnAuroraTextReceived(Text, bPartial);
}

void AAuroraLiveController::HandleGesture(const FString& GestureName, float Intensity)
{
    const float ClampedIntensity = FMath::Clamp(Intensity, 0.0f, 1.0f);
    LastEventType = TEXT("avatar.gesture");

    // Kick off a brief procedural body lean sized by intensity. UpdateProceduralIdleMotion
    // decays this back to rest over GestureDuration, so gestures read as physical emphasis
    // even without dedicated gesture montage assets.
    GestureLeanAmount = ClampedIntensity * GestureLeanDegrees;
    GestureTimer = GestureDuration;

    OnAuroraGestureReceived(GestureName, ClampedIntensity);
}


void AAuroraLiveController::AssignLipSyncGeneratorToAnimInstances()
{
    LastAssignedLipSyncAnimInstanceCount = 0;
    if (!RealisticLipSyncGenerator)
    {
        return;
    }

    if (TargetMeshComponents.Num() == 0 && bAutoDiscoverTargetMeshes)
    {
        DiscoverTargetMeshes();
    }

    static const FName GeneratorPropertyName(TEXT("AuroraLipSyncGenerator"));
    for (USkeletalMeshComponent* Mesh : TargetMeshComponents)
    {
        if (!IsValid(Mesh))
        {
            continue;
        }

        UAnimInstance* AnimInstance = Mesh->GetAnimInstance();
        if (!IsValid(AnimInstance))
        {
            continue;
        }

        FObjectProperty* ObjectProperty = FindFProperty<FObjectProperty>(AnimInstance->GetClass(), GeneratorPropertyName);
        if (!ObjectProperty)
        {
            continue;
        }

        if (!RealisticLipSyncGenerator->IsA(ObjectProperty->PropertyClass))
        {
            UE_LOG(LogTemp, Warning, TEXT("Aurora lip sync property %s on %s expects %s, got %s"),
                *GeneratorPropertyName.ToString(),
                *AnimInstance->GetName(),
                *GetNameSafe(ObjectProperty->PropertyClass),
                *GetNameSafe(RealisticLipSyncGenerator));
            continue;
        }

        ObjectProperty->SetObjectPropertyValue_InContainer(AnimInstance, RealisticLipSyncGenerator);
        ++LastAssignedLipSyncAnimInstanceCount;
        UE_LOG(LogTemp, Log, TEXT("Aurora assigned RealisticLipSyncGenerator to %s.%s"),
            *AnimInstance->GetName(),
            *GeneratorPropertyName.ToString());
    }
}

void AAuroraLiveController::ProcessAuroraPcmAudio(const TArray<float>& PcmData, int32 SampleRate, int32 Channels)
{
    LastPcmSampleRate = SampleRate;
    LastPcmChannels = Channels;
    LastPcmSampleCount = PcmData.Num();

    if (!RealisticLipSyncGenerator)
    {
        FRealisticMetaHumanLipSyncConfig LipSyncConfig;
        LipSyncConfig.ModelType = ERealisticMetaHumanLipSyncModelType::HighlyOptimized;
        RealisticLipSyncGenerator = URealisticMetaHumanLipSyncGenerator::CreateRealisticMetaHumanLipSyncGenerator(LipSyncConfig);
        AssignLipSyncGeneratorToAnimInstances();
    }

    if (!RealisticLipSyncGenerator)
    {
        UE_LOG(LogTemp, Warning, TEXT("Aurora PCM received but RealisticLipSyncGenerator is null"));
        return;
    }

    if (PcmData.Num() == 0 || SampleRate <= 0 || Channels <= 0)
    {
        UE_LOG(LogTemp, Warning, TEXT("Aurora PCM invalid: samples=%d rate=%d channels=%d"), PcmData.Num(), SampleRate, Channels);
        return;
    }

    RealisticLipSyncGenerator->ProcessAudioData(PcmData, SampleRate, Channels);
    UE_LOG(LogTemp, Verbose, TEXT("Aurora PCM processed for MetaHuman lip sync: samples=%d rate=%d channels=%d"), PcmData.Num(), SampleRate, Channels);
}

void AAuroraLiveController::HandleRawEvent(const FString& PayloadJson)
{
    LastPayloadJson = PayloadJson;

    TSharedPtr<FJsonObject> Root;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(PayloadJson);
    if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
    {
        return;
    }

    FString EventType;
    if (!Root->TryGetStringField(TEXT("type"), EventType) || EventType != TEXT("avatar.audio.pcm"))
    {
        return;
    }

    FString AudioBase64;
    FString Format;
    double SampleRateNumber = 16000.0;
    double ChannelsNumber = 1.0;
    Root->TryGetStringField(TEXT("audioBase64"), AudioBase64);
    Root->TryGetStringField(TEXT("format"), Format);
    Root->TryGetNumberField(TEXT("sampleRate"), SampleRateNumber);
    Root->TryGetNumberField(TEXT("channels"), ChannelsNumber);

    TArray<uint8> RawBytes;
    if (AudioBase64.IsEmpty() || !FBase64::Decode(AudioBase64, RawBytes))
    {
        UE_LOG(LogTemp, Warning, TEXT("Aurora audio PCM event had invalid base64 payload"));
        return;
    }

    TArray<float> Samples;
    if (Format.Equals(TEXT("float32"), ESearchCase::IgnoreCase))
    {
        const int32 SampleCount = RawBytes.Num() / sizeof(float);
        Samples.SetNumUninitialized(SampleCount);
        if (SampleCount > 0)
        {
            FMemory::Memcpy(Samples.GetData(), RawBytes.GetData(), SampleCount * sizeof(float));
        }
    }
    else if (Format.Equals(TEXT("int16"), ESearchCase::IgnoreCase))
    {
        const int32 SampleCount = RawBytes.Num() / sizeof(int16);
        Samples.Reserve(SampleCount);
        const int16* IntSamples = reinterpret_cast<const int16*>(RawBytes.GetData());
        for (int32 Index = 0; Index < SampleCount; ++Index)
        {
            Samples.Add(FMath::Clamp(static_cast<float>(IntSamples[Index]) / 32768.0f, -1.0f, 1.0f));
        }
    }
    else
    {
        UE_LOG(LogTemp, Warning, TEXT("Aurora audio PCM unsupported format: %s"), *Format);
        return;
    }

    ProcessAuroraPcmAudio(Samples, static_cast<int32>(SampleRateNumber), static_cast<int32>(ChannelsNumber));
}


void AAuroraLiveController::PrewarmLipSyncGenerator(int32 SampleRate, int32 Channels, int32 DurationMs)
{
    if (SampleRate <= 0 || Channels <= 0 || DurationMs <= 0)
    {
        return;
    }

    const int32 SampleCount = FMath::Max(1, FMath::RoundToInt(static_cast<float>(SampleRate * Channels * DurationMs) / 1000.0f));
    TArray<float> Silence;
    Silence.Init(0.0f, SampleCount);
    LastLipSyncPrewarmSampleCount = SampleCount;
    bLipSyncPrewarmed = true;
    ProcessAuroraPcmAudio(Silence, SampleRate, Channels);
    UE_LOG(LogTemp, Log, TEXT("Aurora prewarmed MetaHuman lip sync generator: samples=%d rate=%d channels=%d durationMs=%d"),
        SampleCount, SampleRate, Channels, DurationMs);
}

namespace
{
    // One control-curve activation within a face pose. Curve is an upper-face
    // MetaHuman control (CTRL_expressions_*); Weight is its peak value (0-1).
    struct FFaceCurveKey
    {
        const TCHAR* Curve;
        float Weight;
    };

    // A named face micro-expression. These co-activation sets are mined from the
    // MetaHuman Face_ROM control vocabulary, pitched at fractional weights so they
    // read as fleeting natural expressions rather than the ROM's full-scale
    // calibration extremes. The library is deliberately skewed warm/playful — Aurora
    // is a vibrant co-host, not a newsreader. Mouth/jaw curves ARE used here (for real
    // smiles/grins) but the caller suppresses them while she is Speaking so the NN lip
    // sync stays the sole mouth driver; when she is idle/listening/thinking her mouth
    // is free and the full expression plays.
    struct FAuroraFacePose
    {
        const TCHAR* Name;
        TArray<FFaceCurveKey> Curves;
    };

    const TArray<FAuroraFacePose>& GetAuroraFacePoseLibrary()
    {
        static const TArray<FAuroraFacePose> Library =
        {
            // --- Warm / vibrant register (the co-host's default mood) ---
            { TEXT("grin"), {
                { TEXT("CTRL_expressions_mouthCornerPullL"), 0.55f }, { TEXT("CTRL_expressions_mouthCornerPullR"), 0.52f },
                { TEXT("CTRL_expressions_mouthDimpleL"), 0.30f }, { TEXT("CTRL_expressions_mouthDimpleR"), 0.28f },
                { TEXT("CTRL_expressions_eyeCheekRaiseL"), 0.40f }, { TEXT("CTRL_expressions_eyeCheekRaiseR"), 0.38f },
                { TEXT("CTRL_expressions_eyeSquintInnerL"), 0.18f }, { TEXT("CTRL_expressions_eyeSquintInnerR"), 0.18f },
            }},
            { TEXT("delight"), {
                // Bright "ooh!" — raised brows, wide eyes, open smile.
                { TEXT("CTRL_expressions_browRaiseInL"), 0.30f }, { TEXT("CTRL_expressions_browRaiseInR"), 0.30f },
                { TEXT("CTRL_expressions_browRaiseOuterL"), 0.34f }, { TEXT("CTRL_expressions_browRaiseOuterR"), 0.32f },
                { TEXT("CTRL_expressions_eyeWidenL"), 0.22f }, { TEXT("CTRL_expressions_eyeWidenR"), 0.22f },
                { TEXT("CTRL_expressions_mouthCornerPullL"), 0.45f }, { TEXT("CTRL_expressions_mouthCornerPullR"), 0.44f },
                { TEXT("CTRL_expressions_jawOpen"), 0.12f },
            }},
            { TEXT("playful"), {
                // Asymmetric cheeky smirk: one corner up, opposite brow cocked.
                { TEXT("CTRL_expressions_mouthCornerPullL"), 0.50f }, { TEXT("CTRL_expressions_mouthDimpleL"), 0.34f },
                { TEXT("CTRL_expressions_browRaiseOuterR"), 0.36f }, { TEXT("CTRL_expressions_eyeCheekRaiseL"), 0.26f },
            }},
            { TEXT("wink"), {
                // Classic silly wink: one eye shut, matching cheeky half-smile.
                { TEXT("CTRL_expressions_eyeBlinkL"), 0.95f }, { TEXT("CTRL_expressions_eyeCheekRaiseL"), 0.42f },
                { TEXT("CTRL_expressions_mouthCornerPullL"), 0.45f }, { TEXT("CTRL_expressions_mouthDimpleL"), 0.30f },
            }},
            { TEXT("amused"), {
                // Suppressed grin — lips pressed, dimples, smiling eyes.
                { TEXT("CTRL_expressions_mouthDimpleL"), 0.42f }, { TEXT("CTRL_expressions_mouthDimpleR"), 0.40f },
                { TEXT("CTRL_expressions_mouthCornerPullL"), 0.28f }, { TEXT("CTRL_expressions_mouthCornerPullR"), 0.26f },
                { TEXT("CTRL_expressions_eyeCheekRaiseL"), 0.34f }, { TEXT("CTRL_expressions_eyeCheekRaiseR"), 0.32f },
            }},
            { TEXT("surprise"), {
                // Big "no way!" pop — high brows, wide eyes, jaw drops a touch.
                { TEXT("CTRL_expressions_browRaiseInL"), 0.42f }, { TEXT("CTRL_expressions_browRaiseInR"), 0.42f },
                { TEXT("CTRL_expressions_browRaiseOuterL"), 0.40f }, { TEXT("CTRL_expressions_browRaiseOuterR"), 0.40f },
                { TEXT("CTRL_expressions_eyeWidenL"), 0.30f }, { TEXT("CTRL_expressions_eyeWidenR"), 0.30f },
                { TEXT("CTRL_expressions_jawOpen"), 0.16f },
            }},
            // --- Thoughtful accents (kept for range, now the minority) ---
            { TEXT("interest"), {
                { TEXT("CTRL_expressions_browRaiseInL"), 0.35f }, { TEXT("CTRL_expressions_browRaiseInR"), 0.33f },
                { TEXT("CTRL_expressions_browRaiseOuterL"), 0.30f }, { TEXT("CTRL_expressions_browRaiseOuterR"), 0.28f },
                { TEXT("CTRL_expressions_eyeWidenL"), 0.14f }, { TEXT("CTRL_expressions_eyeWidenR"), 0.14f },
            }},
            { TEXT("recall"), {
                // Soft "thinking / remembering" brow lift.
                { TEXT("CTRL_expressions_browRaiseInL"), 0.24f }, { TEXT("CTRL_expressions_browRaiseInR"), 0.22f },
                { TEXT("CTRL_expressions_browLateralL"), 0.14f }, { TEXT("CTRL_expressions_browLateralR"), 0.13f },
            }},
            { TEXT("cheeky_skeptic"), {
                // Cocked single brow with a knowing half-smile (not a frown).
                { TEXT("CTRL_expressions_browRaiseOuterL"), 0.45f }, { TEXT("CTRL_expressions_browRaiseInL"), 0.16f },
                { TEXT("CTRL_expressions_eyeSquintInnerR"), 0.12f }, { TEXT("CTRL_expressions_mouthCornerPullL"), 0.20f },
            }},
        };
        return Library;
    }
}

void AAuroraLiveController::ApplyProceduralFacialIdle(float DeltaSeconds)
{
    LastAppliedFacialIdleMorphCount = 0;

    // Blink and eye aim are handled inside the Face ABP. Here we drive the upper
    // face: a continuous asymmetric drift (so it's never frozen between blinks)
    // plus occasional spontaneous micro-expressions mined from the Face_ROM set.
    if (!bEnableProceduralFacialIdle || FacialIdleIntensity <= 0.0f)
    {
        ProceduralBlinkValue = 0.0f;
        ActiveMicroExpressionIndex = INDEX_NONE;
        ActiveMicroExpressionWeight = 0.0f;
        ActiveMicroExpressionName.Reset();
        FAuroraFaceIdleChannel::Publish(TMap<FName, float>());
        return;
    }

    // Lively upper-face life at all times (she's a co-host, not resting), pushed a
    // little further while thinking/speaking. Idle/listening stay high so she never
    // goes flat between turns.
    float StateScale = 0.80f;
    switch (CurrentState)
    {
    case EAuroraAvatarState::Speaking:  StateScale = 1.0f;  break;
    case EAuroraAvatarState::Thinking:  StateScale = 0.90f; break;
    case EAuroraAvatarState::Listening: StateScale = 0.85f; break;
    default:                            StateScale = 0.80f; break;
    }

    // The NN lip sync owns the mouth only while she is actually producing speech.
    // Any other state leaves the mouth free for smiles / silly expressions.
    const bool bMouthFree = (CurrentState != EAuroraAvatarState::Speaking);

    const float T = GetWorld() ? GetWorld()->GetTimeSeconds() : 0.0f;

    // Continuous drift helper: a slow 0..1 oscillation at an incommensurate
    // frequency with a per-side phase offset, so the two brows never lockstep
    // (the old symmetric pair read as robotic).
    auto Drift = [T](float Freq, float Phase)
    {
        return FMath::Sin((T * Freq + Phase) * 2.0f * PI) * 0.5f + 0.5f;
    };

    const float DriftScale = FacialIdleIntensity * StateScale;

    TMap<FName, float> Curves;
    Curves.Reserve(24);
    auto Add = [&Curves](const FName& Name, float Value)
    {
        Curves.FindOrAdd(Name) += Value;
    };

    Add(TEXT("CTRL_expressions_browRaiseInL"),    Drift(0.37f, 0.00f) * 0.16f * DriftScale);
    Add(TEXT("CTRL_expressions_browRaiseInR"),    Drift(0.31f, 0.42f) * 0.16f * DriftScale);
    Add(TEXT("CTRL_expressions_browRaiseOuterL"), Drift(0.29f, 0.15f) * 0.11f * DriftScale);
    Add(TEXT("CTRL_expressions_browRaiseOuterR"), Drift(0.33f, 0.61f) * 0.11f * DriftScale);
    Add(TEXT("CTRL_expressions_eyeSquintInnerL"), Drift(0.53f, 0.20f) * 0.09f * DriftScale);
    Add(TEXT("CTRL_expressions_eyeSquintInnerR"), Drift(0.47f, 0.72f) * 0.09f * DriftScale);
    Add(TEXT("CTRL_expressions_eyeCheekRaiseL"),  Drift(0.23f, 0.33f) * 0.09f * DriftScale);
    Add(TEXT("CTRL_expressions_eyeCheekRaiseR"),  Drift(0.19f, 0.81f) * 0.09f * DriftScale);
    Add(TEXT("CTRL_expressions_noseWrinkleL"),    Drift(0.13f, 0.50f) * 0.05f * DriftScale);
    Add(TEXT("CTRL_expressions_noseWrinkleR"),    Drift(0.17f, 0.90f) * 0.05f * DriftScale);
    // A little playful mouth life on top of the drift (only while the mouth is free) so
    // her lips aren't statue-still between spontaneous poses.
    if (bMouthFree)
    {
        Add(TEXT("CTRL_expressions_mouthCornerPullL"), Drift(0.21f, 0.10f) * 0.10f * DriftScale);
        Add(TEXT("CTRL_expressions_mouthCornerPullR"), Drift(0.19f, 0.55f) * 0.10f * DriftScale);
        Add(TEXT("CTRL_expressions_mouthDimpleL"), Drift(0.27f, 0.35f) * 0.06f * DriftScale);
        Add(TEXT("CTRL_expressions_mouthDimpleR"), Drift(0.25f, 0.85f) * 0.06f * DriftScale);
    }

    // Resting warmth: a gentle baseline smile + smiling eyes so her neutral face reads
    // as an engaged co-host rather than stern. It breathes slightly (so it's never a
    // frozen grin). While the mouth is free it plays at full strength; WHILE SPEAKING a
    // softened version (SpeakingSmileScale) is blended UNDER the NN lip sync — only the
    // mouth-corner raise + cheek raise, which don't contest the visemes — so she looks
    // warm and engaged as she talks rather than dropping to a flat mouth.
    // Slow "smile bloom": she drifts between a relaxed, essentially neutral mouth and a bigger,
    // warmer smile on a long cycle, so she alternates smile<->normal instead of being frozen in a
    // constant half-smile / permanently parted mouth. Pow() biases the cycle toward the low end,
    // so neutral is the resting baseline and the full smile is a periodic bloom. IdleRestingSmile
    // sets the PEAK size of the bloom (bigger value = bigger smile). Micro-expressions (grin,
    // delight, etc.) still layer their own bigger smiles on top at random intervals.
    if (IdleRestingSmile > 0.0f)
    {
        const float SpeechScale = bMouthFree ? 1.0f : FMath::Clamp(SpeakingSmileScale, 0.0f, 1.0f);
        const float Bloom = FMath::Pow(Drift(0.045f, 0.11f), 1.8f); // 0..1, ~22s cycle, rests near 0
        const float RestSmile = IdleRestingSmile * Bloom * SpeechScale;
        if (RestSmile > 0.001f)
        {
            Add(TEXT("CTRL_expressions_mouthCornerPullL"),   RestSmile);
            Add(TEXT("CTRL_expressions_mouthCornerPullR"),   RestSmile * 0.95f);
            Add(TEXT("CTRL_expressions_eyeCheekRaiseL"), RestSmile * 0.55f);
            Add(TEXT("CTRL_expressions_eyeCheekRaiseR"), RestSmile * 0.53f);
        }
    }

    // Spontaneous micro-expression, eased in/out on top of the drift.
    UpdateFacialMicroExpression(DeltaSeconds);
    if (ActiveMicroExpressionIndex != INDEX_NONE)
    {
        const TArray<FAuroraFacePose>& Lib = GetAuroraFacePoseLibrary();
        if (Lib.IsValidIndex(ActiveMicroExpressionIndex))
        {
            const float Contribution = ActiveMicroExpressionWeight * MicroExpressionIntensity * StateScale;
            bool bPoseClosesLeftEye = false;
            for (const FFaceCurveKey& Key : Lib[ActiveMicroExpressionIndex].Curves)
            {
                // While speaking, drop the mouth/jaw channels of the pose so the NN lip
                // sync is never contested; the upper-face part still plays.
                if (!bMouthFree)
                {
                    const FString KeyName(Key.Curve);
                    if (KeyName.Contains(TEXT("mouth")) || KeyName.Contains(TEXT("jaw")))
                    {
                        continue;
                    }
                }
                bPoseClosesLeftEye |= (FCString::Strcmp(Key.Curve, TEXT("CTRL_expressions_eyeBlinkL")) == 0);
                Add(Key.Curve, Key.Weight * Contribution);
            }

            // A wink owns the eyes: cancel the ABP's auto-blink on the OPEN eye while the
            // wink holds (negative additive value; the anim node floors the final curve at
            // 0). Otherwise a periodic blink shuts the open eye mid-wink and the wink reads
            // as a stutter. Tracks the ease weight so suppression fades with the wink.
            if (bPoseClosesLeftEye)
            {
                Add(TEXT("CTRL_expressions_eyeBlinkR"), -ActiveMicroExpressionWeight);
            }
        }
    }

    // Publish the computed curves for FAnimNode_AuroraFaceIdle (our custom anim node placed
    // LAST before Output in ABP_Aurora_Face, downstream of BlendRealisticMetaHumanLipSync —
    // that lipsync node overwrites every raw face curve it knows about each frame, so anything
    // injected earlier dies). The node pulls these on the anim thread; writing compiled anim
    // node structs directly from here is silently discarded by the anim runtime (verified).
    // Curve names must be RigLogic RAW controls (mouthCornerPull*, not mouthSmile* — this
    // MetaHuman has no mouthSmile control). Final output curves feed ABP_Face_PostProcess's
    // RigLogic, which is what visibly drives the face.
    // Negative values are legitimate here: they suppress an upstream curve (auto-blink
    // during a wink) — the anim node clamps the final applied result to the rig's 0..1.
    for (TPair<FName, float>& Curve : Curves)
    {
        Curve.Value = FMath::Clamp(Curve.Value, -1.0f, 1.0f);
    }
    FAuroraFaceIdleChannel::Publish(Curves);
    LastAppliedFacialIdleMorphCount = Curves.Num();
    FacialIdleDebug = FString::Printf(TEXT("published %d curves"), Curves.Num());
}

FAnimNode_ModifyCurve* AAuroraLiveController::FindFaceModifyCurveNode(UAnimInstance* AnimInstance)
{
    if (!AnimInstance)
    {
        return nullptr;
    }

    // Walk the generated anim BP class's node properties and return the first ModifyCurve node.
    // ABP_Aurora_Face has exactly one (the idle-expression injector we added upstream of the
    // ControlRig); the body mesh's anim instance has none, so it's skipped.
    if (IAnimClassInterface* AnimClass = IAnimClassInterface::GetFromClass(AnimInstance->GetClass()))
    {
        for (const FStructProperty* NodeProp : AnimClass->GetAnimNodeProperties())
        {
            if (NodeProp && NodeProp->Struct && NodeProp->Struct->IsChildOf(FAnimNode_ModifyCurve::StaticStruct()))
            {
                return NodeProp->ContainerPtrToValuePtr<FAnimNode_ModifyCurve>(AnimInstance);
            }
        }
    }

    return nullptr;
}

void AAuroraLiveController::UpdateFacialMicroExpression(float DeltaSeconds)
{
    if (!bEnableFacialMicroExpressions)
    {
        ActiveMicroExpressionIndex = INDEX_NONE;
        ActiveMicroExpressionWeight = 0.0f;
        ActiveMicroExpressionName.Reset();
        return;
    }

    // Envelope for a single expression: ease in, hold, ease out (seconds).
    const float BlendIn = 0.35f;
    const float BlendOut = 0.55f;

    if (ActiveMicroExpressionIndex == INDEX_NONE)
    {
        MicroExpressionTimer -= DeltaSeconds;
        if (MicroExpressionTimer > 0.0f)
        {
            return;
        }

        const TArray<FAuroraFacePose>& Lib = GetAuroraFacePoseLibrary();
        if (Lib.Num() == 0)
        {
            return;
        }

        // Pick a new pose, avoiding an immediate repeat of the last one.
        int32 NewIndex = FMath::RandRange(0, Lib.Num() - 1);
        if (Lib.Num() > 1 && NewIndex == LastMicroExpressionIndex)
        {
            NewIndex = (NewIndex + 1) % Lib.Num();
        }

        ActiveMicroExpressionIndex = NewIndex;
        LastMicroExpressionIndex = NewIndex;
        ActiveMicroExpressionName = Lib[NewIndex].Name;
        MicroExpressionElapsed = 0.0f;
        MicroExpressionHold = FMath::FRandRange(0.5f, 1.6f);
        ActiveMicroExpressionWeight = 0.0f;
        return;
    }

    MicroExpressionElapsed += DeltaSeconds;
    const float Total = BlendIn + MicroExpressionHold + BlendOut;

    float LinearWeight;
    if (MicroExpressionElapsed < BlendIn)
    {
        LinearWeight = MicroExpressionElapsed / BlendIn;
    }
    else if (MicroExpressionElapsed < BlendIn + MicroExpressionHold)
    {
        LinearWeight = 1.0f;
    }
    else if (MicroExpressionElapsed < Total)
    {
        LinearWeight = 1.0f - (MicroExpressionElapsed - BlendIn - MicroExpressionHold) / BlendOut;
    }
    else
    {
        // Finished: go quiet and schedule the next spontaneous expression.
        ActiveMicroExpressionIndex = INDEX_NONE;
        ActiveMicroExpressionWeight = 0.0f;
        ActiveMicroExpressionName.Reset();
        const float MaxInterval = FMath::Max(MicroExpressionIntervalMin, MicroExpressionIntervalMax);
        MicroExpressionTimer = FMath::FRandRange(MicroExpressionIntervalMin, MaxInterval);
        return;
    }

    // Smoothstep the linear envelope for a soft, organic ramp.
    ActiveMicroExpressionWeight = FMath::SmoothStep(0.0f, 1.0f, FMath::Clamp(LinearWeight, 0.0f, 1.0f));
}

void AAuroraLiveController::UpdateProceduralIdleMotion(float DeltaSeconds)
{
    if (!bEnableProceduralIdleMotion)
    {
        return;
    }

    // Resolve the character actor to animate (the MetaHuman), not this controller.
    AActor* Actor = TargetActor ? TargetActor.Get() : nullptr;
    if (!Actor && TargetMeshComponents.Num() > 0 && IsValid(TargetMeshComponents[0]))
    {
        Actor = TargetMeshComponents[0]->GetOwner();
    }
    if (!Actor)
    {
        return;
    }

    // Capture the rest pose once (and re-capture if the target actor changes) so the
    // procedural offsets are always relative to the authored placement.
    if (!bHasProceduralBaseTransform || ProceduralMotionActor.Get() != Actor)
    {
        ProceduralBaseLocation = Actor->GetActorLocation();
        ProceduralBaseRotation = Actor->GetActorRotation();
        ProceduralMotionActor = Actor;
        bHasProceduralBaseTransform = true;
    }

    StateElapsedSeconds += DeltaSeconds;

    // More overt motion while speaking, calmer while idle/listening.
    float TargetIntensity = 0.35f;
    switch (CurrentState)
    {
    case EAuroraAvatarState::Speaking:  TargetIntensity = 1.0f;  break;
    case EAuroraAvatarState::Thinking:  TargetIntensity = 0.7f;  break;
    case EAuroraAvatarState::Listening: TargetIntensity = 0.5f;  break;
    case EAuroraAvatarState::Idle:
    default:                            TargetIntensity = 0.35f; break;
    }
    ProceduralMotionIntensity = FMath::FInterpTo(ProceduralMotionIntensity, TargetIntensity, DeltaSeconds, 2.0f);

    const float T = GetWorld() ? GetWorld()->GetTimeSeconds() : StateElapsedSeconds;

    // Translation offsets are authored in cm at 1x, so scale them by the character's
    // own scale — otherwise a scaled-up MetaHuman reads as barely breathing (the cm
    // move stays constant while her body grows). Rotations (yaw/lean) are in degrees
    // and look identical at any scale, so they are left unscaled.
    const float MotionScale = Actor->GetActorScale3D().Z;

    // Breathing: gentle vertical rise/fall. Sway + yaw: slow weight shifts on
    // incommensurate frequencies so the loop never reads as periodic.
    const float BobZ  = FMath::Sin(T * BreathingRateHz * 2.0f * PI) * IdleBobAmplitude * ProceduralMotionIntensity * MotionScale;
    const float SwayX = FMath::Sin(T * 0.13f * 2.0f * PI) * IdleBobAmplitude * 0.5f * ProceduralMotionIntensity * MotionScale;
    const float Yaw   = FMath::Sin(T * 0.11f * 2.0f * PI) * IdleYawAmplitudeDegrees * ProceduralMotionIntensity;

    // Decay any active gesture impulse into a brief forward lean.
    float GestureLean = 0.0f;
    if (GestureTimer > 0.0f && GestureDuration > 0.0f)
    {
        GestureTimer = FMath::Max(0.0f, GestureTimer - DeltaSeconds);
        GestureLean = GestureLeanAmount * (GestureTimer / GestureDuration);
    }

    const FVector NewLocation = ProceduralBaseLocation + FVector(SwayX, 0.0f, BobZ);
    const FRotator NewRotation = ProceduralBaseRotation + FRotator(GestureLean, Yaw, 0.0f);
    Actor->SetActorLocationAndRotation(NewLocation, NewRotation);
}
