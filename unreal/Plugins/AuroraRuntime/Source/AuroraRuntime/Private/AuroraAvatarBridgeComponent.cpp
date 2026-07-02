#include "AuroraAvatarBridgeComponent.h"

#include "Dom/JsonObject.h"
#include "IWebSocket.h"
#include "Serialization/JsonReader.h"
#include "Serialization/JsonSerializer.h"
#include "WebSocketsModule.h"

UAuroraAvatarBridgeComponent::UAuroraAvatarBridgeComponent()
{
    PrimaryComponentTick.bCanEverTick = false;
}

void UAuroraAvatarBridgeComponent::BeginPlay()
{
    Super::BeginPlay();
    if (bAutoConnect)
    {
        Connect();
    }
}

void UAuroraAvatarBridgeComponent::EndPlay(const EEndPlayReason::Type EndPlayReason)
{
    Disconnect();
    Super::EndPlay(EndPlayReason);
}

void UAuroraAvatarBridgeComponent::Connect()
{
    if (Socket.IsValid() && Socket->IsConnected())
    {
        return;
    }

    if (!FModuleManager::Get().IsModuleLoaded(TEXT("WebSockets")))
    {
        FModuleManager::Get().LoadModule(TEXT("WebSockets"));
    }

    Socket = FWebSocketsModule::Get().CreateWebSocket(BridgeUrl);
    Socket->OnConnected().AddUObject(this, &UAuroraAvatarBridgeComponent::HandleConnected);
    Socket->OnConnectionError().AddUObject(this, &UAuroraAvatarBridgeComponent::HandleConnectionError);
    Socket->OnClosed().AddUObject(this, &UAuroraAvatarBridgeComponent::HandleClosed);
    Socket->OnMessage().AddUObject(this, &UAuroraAvatarBridgeComponent::HandleMessage);
    Socket->Connect();
}

void UAuroraAvatarBridgeComponent::Disconnect()
{
    if (Socket.IsValid())
    {
        Socket->Close();
        Socket.Reset();
    }
    if (bConnected)
    {
        bConnected = false;
        OnAuroraConnectionChanged.Broadcast(false);
    }
}

void UAuroraAvatarBridgeComponent::HandleConnected()
{
    bConnected = true;
    OnAuroraConnectionChanged.Broadcast(true);
}

void UAuroraAvatarBridgeComponent::HandleConnectionError(const FString& Error)
{
    bConnected = false;
    UE_LOG(LogTemp, Warning, TEXT("Aurora bridge connection error: %s"), *Error);
    OnAuroraConnectionChanged.Broadcast(false);
}

void UAuroraAvatarBridgeComponent::HandleClosed(int32 StatusCode, const FString& Reason, bool bWasClean)
{
    bConnected = false;
    UE_LOG(LogTemp, Log, TEXT("Aurora bridge closed: code=%d clean=%d reason=%s"), StatusCode, bWasClean, *Reason);
    OnAuroraConnectionChanged.Broadcast(false);
}

void UAuroraAvatarBridgeComponent::ApplyStateString(const FString& StateString)
{
    CurrentStateString = StateString;
    if (StateString.Equals(TEXT("listening"), ESearchCase::IgnoreCase))
    {
        CurrentState = EAuroraAvatarState::Listening;
    }
    else if (StateString.Equals(TEXT("thinking"), ESearchCase::IgnoreCase))
    {
        CurrentState = EAuroraAvatarState::Thinking;
    }
    else if (StateString.Equals(TEXT("speaking"), ESearchCase::IgnoreCase))
    {
        CurrentState = EAuroraAvatarState::Speaking;
    }
    else
    {
        CurrentState = EAuroraAvatarState::Idle;
        CurrentStateString = TEXT("idle");
    }
}

void UAuroraAvatarBridgeComponent::HandleMessage(const FString& Message)
{
    LastPayloadJson = Message;
    OnAuroraRawEvent.Broadcast(Message);

    TSharedPtr<FJsonObject> Root;
    const TSharedRef<TJsonReader<>> Reader = TJsonReaderFactory<>::Create(Message);
    if (!FJsonSerializer::Deserialize(Reader, Root) || !Root.IsValid())
    {
        UE_LOG(LogTemp, Warning, TEXT("Aurora bridge received invalid JSON: %s"), *Message);
        return;
    }

    FString EventType;
    if (!Root->TryGetStringField(TEXT("type"), EventType))
    {
        return;
    }
    LastEventType = EventType;

    if (EventType == TEXT("avatar.state"))
    {
        FString StateString;
        if (Root->TryGetStringField(TEXT("state"), StateString))
        {
            ApplyStateString(StateString);
            OnAuroraStateChanged.Broadcast(CurrentState, CurrentStateString);
        }
    }
    else if (EventType == TEXT("avatar.lipsync.amplitude"))
    {
        const TArray<TSharedPtr<FJsonValue>>* ValuesJson = nullptr;
        TArray<float> Values;
        if (Root->TryGetArrayField(TEXT("values"), ValuesJson) && ValuesJson)
        {
            Values.Reserve(ValuesJson->Num());
            for (const TSharedPtr<FJsonValue>& Value : *ValuesJson)
            {
                Values.Add(FMath::Clamp(static_cast<float>(Value->AsNumber()), 0.0f, 1.0f));
            }
        }

        if (Values.Num() > 0)
        {
            float Sum = 0.0f;
            for (float Value : Values)
            {
                Sum += Value;
            }
            MouthOpen = FMath::Clamp(Sum / static_cast<float>(Values.Num()), 0.0f, 1.0f);
        }
        else
        {
            MouthOpen = 0.0f;
        }
        OnAuroraLipSync.Broadcast(MouthOpen, Values);
    }
    else if (EventType == TEXT("avatar.text.partial") || EventType == TEXT("avatar.text.final"))
    {
        FString Text;
        Root->TryGetStringField(TEXT("text"), Text);
        OnAuroraText.Broadcast(Text, EventType == TEXT("avatar.text.partial"));
    }
    else if (EventType == TEXT("avatar.gesture"))
    {
        FString GestureName;
        double Intensity = 1.0;
        Root->TryGetStringField(TEXT("name"), GestureName);
        Root->TryGetNumberField(TEXT("intensity"), Intensity);
        OnAuroraGesture.Broadcast(GestureName, FMath::Clamp(static_cast<float>(Intensity), 0.0f, 1.0f));
    }
}
