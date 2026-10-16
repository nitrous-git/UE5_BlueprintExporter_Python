import os

import unreal

from CodeXAI import config
from CodeXAI import io_utils

from CodeXAI.graphs import raw_exporter


# ============================================================================
# Default proof asset
# ============================================================================


DEFAULT_BLUEPRINT = (
    "/Game/CodeX_Restruct/"
    "Frameworks/PlayerFramework/Core/Components/"
    "AC_PlayerAttunementComponent"
)


# ============================================================================
# Helpers
# ============================================================================


def _relative_package(package_name):
    """
    Convert:

        /Game/CodeX_Restruct/Frameworks/...

    into:

        Frameworks/...
    """

    root = config.ROOT_PATH.rstrip("/")
    package_name = package_name.rstrip("/")

    prefix = root + "/"

    if package_name.startswith(prefix):
        return package_name[len(prefix):]

    return package_name.lstrip("/")


def _load_blueprint(package_name):
    """
    Load a Blueprint asset read-only.
    """

    asset = unreal.EditorAssetLibrary.load_asset(
        package_name
    )

    if asset is None:

        raise RuntimeError(
            "Unable to load asset: {}".format(
                package_name
            )
        )

    blueprint = unreal.BlueprintEditorLibrary.get_blueprint_asset(
        asset
    )

    if blueprint is None:

        # Most normal Blueprint assets already ARE UBlueprint objects,
        # but keep a defensive fallback.
        try:
            if isinstance(
                asset,
                unreal.Blueprint
            ):
                blueprint = asset
        except Exception:
            pass

    if blueprint is None:

        raise RuntimeError(
            "Asset is not recognized as a Blueprint: {}".format(
                package_name
            )
        )

    return blueprint


def _log_result(label, result):
    """
    Compact Output Log reporting.
    """

    unreal.log(
        "[CodeXAI] {} success: {}".format(
            label,
            result.get("success", False)
        )
    )

    unreal.log(
        "[CodeXAI] {} file: {}".format(
            label,
            result.get("filename")
        )
    )

    unreal.log(
        "[CodeXAI] {} size: {} bytes".format(
            label,
            result.get(
                "file_size_bytes",
                0
            )
        )
    )

    errors = result.get(
        "errors",
        []
    )

    for error in errors:

        unreal.log_warning(
            "[CodeXAI] {} export: {}".format(
                label,
                error
            )
        )


def _log_diagnostics(label, diagnostics):

    if not diagnostics.get(
        "exists",
        False
    ):

        unreal.log_warning(
            "[CodeXAI] {} T3D does not exist.".format(
                label
            )
        )

        return

    markers = diagnostics.get(
        "markers",
        {}
    )

    unreal.log(
        "[CodeXAI] {} diagnostics:".format(
            label
        )
    )

    unreal.log(
        "[CodeXAI]   Lines: {}".format(
            diagnostics.get(
                "line_count",
                0
            )
        )
    )

    unreal.log(
        "[CodeXAI]   Node blocks: {}".format(
            markers.get(
                "node_blocks",
                0
            )
        )
    )

    unreal.log(
        "[CodeXAI]   Pins: {}".format(
            markers.get(
                "custom_properties_pin",
                0
            )
        )
    )

    unreal.log(
        "[CodeXAI]   Linked pins: {}".format(
            markers.get(
                "linked_to",
                0
            )
        )
    )

    unreal.log(
        "[CodeXAI]   Node GUIDs: {}".format(
            markers.get(
                "node_guid",
                0
            )
        )
    )

    unreal.log(
        "[CodeXAI]   Pin IDs: {}".format(
            markers.get(
                "pin_id",
                0
            )
        )
    )

    unreal.log(
        "[CodeXAI]   Contains graph topology: {}".format(
            diagnostics.get(
                "contains_expected_graph_data",
                False
            )
        )
    )


# ============================================================================
# Probe
# ============================================================================


def run(package_name=DEFAULT_BLUEPRINT):
    """
    Commit 3 proof.

    Export:
        1. whole Blueprint UObject
        2. primary EventGraph UObject

    We intentionally test both boundaries before building the real parser.
    """

    unreal.log(
        "[CodeXAI] ========================================"
    )

    unreal.log(
        "[CodeXAI] Commit 3 - Blueprint T3D Probe"
    )

    unreal.log(
        "[CodeXAI] Blueprint: {}".format(
            package_name
        )
    )

    unreal.log(
        "[CodeXAI] ========================================"
    )

    blueprint = _load_blueprint(
        package_name
    )

    relative_package = _relative_package(
        package_name
    )

    asset_directory = io_utils.asset_output_directory(
        relative_package
    )

    raw_directory = os.path.join(
        asset_directory,
        "_raw"
    )

    os.makedirs(
        raw_directory,
        exist_ok=True
    )

    # ========================================================================
    # 1. Whole Blueprint object
    # ========================================================================

    blueprint_filename = os.path.join(
        raw_directory,
        "blueprint.t3d"
    )

    blueprint_export = raw_exporter.export_object_t3d(
        blueprint,
        blueprint_filename
    )

    blueprint_diagnostics = raw_exporter.inspect_t3d(
        blueprint_filename
    )

    _log_result(
        "Blueprint",
        blueprint_export
    )

    _log_diagnostics(
        "Blueprint",
        blueprint_diagnostics
    )

    # ========================================================================
    # 2. Primary EventGraph
    # ========================================================================

    event_graph = (
        unreal.BlueprintEditorLibrary.find_event_graph(
            blueprint
        )
    )

    event_graph_export = None
    event_graph_diagnostics = None

    if event_graph is None:

        unreal.log_warning(
            "[CodeXAI] Blueprint has no primary EventGraph."
        )

    else:

        event_graph_filename = os.path.join(
            raw_directory,
            "EventGraph.t3d"
        )

        event_graph_export = (
            raw_exporter.export_object_t3d(
                event_graph,
                event_graph_filename
            )
        )

        event_graph_diagnostics = (
            raw_exporter.inspect_t3d(
                event_graph_filename
            )
        )

        _log_result(
            "EventGraph",
            event_graph_export
        )

        _log_diagnostics(
            "EventGraph",
            event_graph_diagnostics
        )

    # ========================================================================
    # Probe manifest
    # ========================================================================

    result = {
        "schema_version": 1,

        "blueprint": package_name,

        "blueprint_export": blueprint_export,

        "blueprint_diagnostics": (
            blueprint_diagnostics
        ),

        "event_graph_export": (
            event_graph_export
        ),

        "event_graph_diagnostics": (
            event_graph_diagnostics
        ),
    }

    probe_path = os.path.join(
        raw_directory,
        "probe.json"
    )

    io_utils.write_json(
        probe_path,
        result
    )

    unreal.log(
        "[CodeXAI] ----------------------------------------"
    )

    unreal.log(
        "[CodeXAI] Probe manifest: {}".format(
            probe_path
        )
    )

    unreal.log(
        "[CodeXAI] ========================================"
    )

    return result