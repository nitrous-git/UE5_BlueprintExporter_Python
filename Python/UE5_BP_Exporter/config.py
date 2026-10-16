"""Generic project configuration (all paths are configurable).

Designed to work unchanged in a new Unreal project. For larger projects,
set ROOT_PATH to the gameplay folder (e.g. /Game/MyGame or /Game/Frameworks).
Exports are read-only with respect to Unreal assets.
"""

# Unreal Asset Registry package root.
ROOT_PATH = "/Game"

# Generated text is written to <Project>/Saved/Blueprint_Context by default.
# A separate local folder/repository may be specified; never choose Content/.
EXTERNAL_OUTPUT_ROOT = None
OUTPUT_FOLDER_NAME = "Blueprint_Context"
MIRROR_FOLDER_NAME = "Game"

# Optional project-specific filters (Unreal package paths).
EXCLUDED_PATHS = []
EXCLUDED_ASSETS = set()
DEPRECATED_NAME_MARKERS = ()

# Full Blueprint graph extraction.
FULL_GRAPH_CLASS_NAMES = {
    "Blueprint",
    "WidgetBlueprint",
    "AnimBlueprint",
}

# Structured source output, not K2 graphs.
STRUCTURAL_CLASS_NAMES = {
    "BehaviorTree",
    "BlackboardData",
    "UserDefinedStruct",
    "UserDefinedEnum",
    "DataTable",
    "InputAction",
    "InputMappingContext",
    "DataAsset",
    "PrimaryDataAsset",
    "StateTree",
}

# Secondary identification for DataAsset instances or generated subclasses.
STRUCTURAL_NAME_PREFIXES = (
    "DA_", "DT_", "BB_", "BT_", "IA_", "IMC_",
)

# Known presentation/content classes; never discard unknown classes silently.
IGNORE_CLASS_NAMES = {
    # Geometry / skeletons
    "StaticMesh", "SkeletalMesh", "Skeleton", "PhysicsAsset",
    # Materials / textures
    "Material", "MaterialInstance", "MaterialInstanceConstant",
    "MaterialFunction", "MaterialFunctionInstance",
    "MaterialParameterCollection", "Texture2D", "TextureCube",
    "TextureRenderTarget2D", "TextureRenderTargetCube",
    "SubsurfaceProfile", "PhysicalMaterial", "RuntimeVirtualTexture",
    # Animation data (NOT AnimBlueprint)
    "AnimSequence", "AnimMontage", "BlendSpace", "BlendSpace1D",
    "AimOffsetBlendSpace", "AimOffsetBlendSpace1D", "PoseAsset",
    "CameraAnimationSequence", "ContextualAnimSceneAsset",
    "ContextualAnimRolesAsset", "IKRigDefinition", "IKRetargeter",
    # VFX
    "NiagaraSystem", "NiagaraEmitter", "NiagaraEffectType",
    "NiagaraScript", "ParticleSystem", "VectorFieldStatic",
    # Audio
    "SoundWave", "SoundCue", "SoundAttenuation", "MetaSoundSource",
    # Maps, world data and foliage
    "World", "MapBuildDataRegistry", "DataLayerAsset", "HLODLayer",
    "LandscapeGrassType", "LandscapeLayerInfoObject", "FoliageType",
    "FoliageType_InstancedStaticMesh",
    # Cinematics / curves / UI presentation
    "LevelSequence", "CurveFloat", "CurveVector", "CurveLinearColor",
    "CurveLinearColorAtlas", "Font", "FontFace",
    "SlateWidgetStyleAsset",
    # Moved/renamed asset redirectors
    "ObjectRedirector",
}

# Deterministic export ordering keeps Git changes readable.
SORT_RESULTS = True
