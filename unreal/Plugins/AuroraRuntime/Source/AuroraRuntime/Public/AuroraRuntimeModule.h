#pragma once

#include "Modules/ModuleManager.h"

class FAuroraRuntimeModule : public IModuleInterface
{
public:
    virtual void StartupModule() override;
    virtual void ShutdownModule() override;
};
