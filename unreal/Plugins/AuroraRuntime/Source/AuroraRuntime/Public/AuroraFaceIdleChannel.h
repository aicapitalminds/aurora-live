#pragma once

#include "CoreMinimal.h"

// Thread-safe mailbox between AAuroraLiveController (game thread, publishes the computed
// facial-idle curve values every tick) and FAnimNode_AuroraFaceIdle (anim worker thread,
// consumes them during graph update). Direct writes into compiled anim node structs are
// silently discarded by the anim runtime (verified 2026-07-01), so the node PULLS from
// here instead of anything pushing into node memory.
struct AURORARUNTIME_API FAuroraFaceIdleChannel
{
    // Replaces the published curve set. Pass empty to clear (face returns to neutral).
    static void Publish(const TMap<FName, float>& Curves);

    // Copies the latest published curve set into OutCurves. Safe from any thread.
    static void Consume(TMap<FName, float>& OutCurves);

private:
    static FCriticalSection Mutex;
    static TMap<FName, float> Published;
};
