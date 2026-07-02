using UnrealBuildTool;

public class AuroraRuntimeEditor : ModuleRules
{
    public AuroraRuntimeEditor(ReadOnlyTargetRules Target) : base(Target)
    {
        PCHUsage = ModuleRules.PCHUsageMode.UseExplicitOrSharedPCHs;

        PublicDependencyModuleNames.AddRange(new string[]
        {
            "Core",
            "CoreUObject",
            "Engine",
            "AuroraRuntime",
            "AnimGraph",
            "BlueprintGraph"
        });

        PrivateDependencyModuleNames.AddRange(new string[]
        {
            "UnrealEd",
            "AnimGraphRuntime"
        });
    }
}
