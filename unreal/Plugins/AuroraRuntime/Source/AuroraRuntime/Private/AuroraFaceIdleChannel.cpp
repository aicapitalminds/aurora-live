#include "AuroraFaceIdleChannel.h"

FCriticalSection FAuroraFaceIdleChannel::Mutex;
TMap<FName, float> FAuroraFaceIdleChannel::Published;

void FAuroraFaceIdleChannel::Publish(const TMap<FName, float>& Curves)
{
    FScopeLock Lock(&Mutex);
    Published = Curves;
}

void FAuroraFaceIdleChannel::Consume(TMap<FName, float>& OutCurves)
{
    FScopeLock Lock(&Mutex);
    OutCurves = Published;
}
