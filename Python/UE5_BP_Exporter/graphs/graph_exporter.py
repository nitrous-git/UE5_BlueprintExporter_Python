import json
import os
import re

import unreal

from CodeXAI import config
from CodeXAI import io_utils

from CodeXAI.graphs import raw_exporter
from CodeXAI.graphs import t3d_parser


# ============================================================================
# Helpers
# ============================================================================


def _safe_filename(name):
    """
    Windows-safe deterministic graph filename.
    """

    sanitized = re.sub(
        r'[<>:"/\\|?*]+',
        "_",
        str(name)
    )

    sanitized = sanitized.strip(
        " ."
    )

    return (
        sanitized
        or "UnnamedGraph"
    )


def _load_blueprint(package_name):
    asset = unreal.EditorAssetLibrary.load_asset(
        package_name
    )

    if asset is None:
        raise RuntimeError(
            "Unable to load asset: {}".format(
                package_name
            )
        )

    blueprint = (
        unreal.BlueprintEditorLibrary.get_blueprint_asset(
            asset
        )
    )

    if blueprint is None:

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


def _read_json(filename):
    with open(
        filename,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(
            file
        )


def _update_asset_json(
    asset_directory,
    parsed_index
):
    """
    Commit 2 intentionally left Blueprint variables and full graph inventory
    deferred. Commit 3 now fills those fields from T3D.
    """

    asset_json_path = os.path.join(
        asset_directory,
        "asset.json"
    )

    if not os.path.isfile(
        asset_json_path
    ):
        return

    document = _read_json(
        asset_json_path
    )

    blueprint = document.setdefault(
        "blueprint",
        {}
    )

    blueprint["variables"] = (
        parsed_index["variables"]
    )

    authored_graphs = (
        parsed_index["graphs"]
    )

    blueprint["graphs"] = {
        "event_graphs": [
            graph["name"]
            for graph in authored_graphs
            if graph["kind"] == "event"
        ],

        "functions": [
            graph["name"]
            for graph in authored_graphs
            if graph["kind"] == "function"
        ],

        "macros": [
            graph["name"]
            for graph in authored_graphs
            if graph["kind"] == "macro"
        ],

        "delegates": [
            graph["name"]
            for graph in authored_graphs
            if graph["kind"] == "delegate"
        ],

        "generated_graphs": [
            graph["name"]
            for graph in parsed_index[
                "generated_graphs"
            ]
        ],
    }

    blueprint["graph_source"] = {
        "index": "blueprint_graphs.json",
        "raw_t3d": "_raw/blueprint.t3d",
        "graph_directory": "graphs",
    }

    extraction_status = blueprint.setdefault(
        "extraction_status",
        {}
    )

    extraction_status[
        "member_variables"
    ] = "complete"

    extraction_status[
        "graph_inventory"
    ] = "complete"

    extraction_status[
        "graph_nodes"
    ] = "complete"

    io_utils.write_json(
        asset_json_path,
        document
    )


def _validate_against_raw(
    parsed,
    diagnostics
):
    warnings = []

    stats = parsed["index"]["stats"]

    parsed_node_count = (
        stats["authored_node_count"]
        +
        stats["generated_node_count"]
    )

    parsed_pin_count = (
        stats["authored_pin_count"]
        +
        stats["generated_pin_count"]
    )

    markers = diagnostics.get(
        "markers",
        {}
    )

    raw_node_count = markers.get(
        "node_guid",
        0
    )

    raw_pin_count = markers.get(
        "custom_properties_pin",
        0
    )

    if (
        raw_node_count
        and parsed_node_count != raw_node_count
    ):

        warnings.append(
            "Parsed node count {} does not match raw T3D marker count {}."
            .format(
                parsed_node_count,
                raw_node_count
            )
        )

    if (
        raw_pin_count
        and parsed_pin_count != raw_pin_count
    ):

        warnings.append(
            "Parsed pin count {} does not match raw T3D marker count {}."
            .format(
                parsed_pin_count,
                raw_pin_count
            )
        )

    return warnings


# ============================================================================
# One Blueprint
# ============================================================================


def _export_one_blueprint(candidate):
    package_name = candidate[
        "package_name"
    ]

    blueprint = _load_blueprint(
        package_name
    )

    asset_directory = (
        io_utils.asset_output_directory(
            candidate[
                "relative_package"
            ]
        )
    )

    raw_directory = os.path.join(
        asset_directory,
        "_raw"
    )

    graph_directory = os.path.join(
        asset_directory,
        "graphs"
    )

    os.makedirs(
        raw_directory,
        exist_ok=True
    )

    os.makedirs(
        graph_directory,
        exist_ok=True
    )

    raw_filename = os.path.join(
        raw_directory,
        "blueprint.t3d"
    )

    raw_result = (
        raw_exporter.export_object_t3d(
            blueprint,
            raw_filename
        )
    )

    if not raw_result.get(
        "success",
        False
    ):

        raise RuntimeError(
            "T3D export failed: {}".format(
                raw_result.get(
                    "errors",
                    []
                )
            )
        )

    diagnostics = (
        raw_exporter.inspect_t3d(
            raw_filename
        )
    )

    parsed = (
        t3d_parser.parse_blueprint_file(
            raw_filename
        )
    )

    index = parsed[
        "index"
    ]

    # ------------------------------------------------------------------------
    # Per-graph normalized source
    # ------------------------------------------------------------------------

    graph_files = []

    for graph_document in parsed[
        "authored_graphs"
    ]:

        graph_name = graph_document[
            "graph"
        ]["name"]

        graph_filename = (
            _safe_filename(
                graph_name
            )
            + ".json"
        )

        graph_path = os.path.join(
            graph_directory,
            graph_filename
        )

        io_utils.write_json(
            graph_path,
            graph_document
        )

        graph_files.append({
            "name": graph_name,
            "kind": graph_document[
                "graph"
            ]["kind"],
            "file": (
                "graphs/"
                + graph_filename
            ),
        })

    graph_files.sort(
        key=lambda item: (
            item["kind"],
            item["name"].lower()
        )
    )

    index["graph_files"] = (
        graph_files
    )

    # ------------------------------------------------------------------------
    # Blueprint graph index
    # ------------------------------------------------------------------------

    index_path = os.path.join(
        asset_directory,
        "blueprint_graphs.json"
    )

    io_utils.write_json(
        index_path,
        index
    )

    # ------------------------------------------------------------------------
    # Fill Commit-2 deferred metadata
    # ------------------------------------------------------------------------

    _update_asset_json(
        asset_directory,
        index
    )

    warnings = _validate_against_raw(
        parsed,
        diagnostics
    )

    return {
        "package_name": package_name,

        "raw_t3d_bytes": raw_result.get(
            "file_size_bytes",
            0
        ),

        "authored_graph_count": index[
            "stats"
        ]["authored_graph_count"],

        "generated_graph_count": index[
            "stats"
        ]["generated_graph_count"],

        "node_count": index[
            "stats"
        ]["authored_node_count"],

        "pin_count": index[
            "stats"
        ]["authored_pin_count"],

        "connection_count": index[
            "stats"
        ]["authored_connection_count"],

        "variable_count": len(
            index["variables"]
        ),

        "warnings": warnings,
    }




def export_single(package_name):
    """
    Export/parse one Blueprint without running the full 184-asset sweep.

    Useful while validating Commit 3 against representative Blueprint types.
    """

    root = config.ROOT_PATH.rstrip("/")
    package_name = str(package_name).rstrip("/")

    prefix = root + "/"

    if not package_name.startswith(prefix):
        raise RuntimeError(
            "Blueprint is outside configured CodeX root: {}".format(
                package_name
            )
        )

    candidate = {
        "package_name": package_name,
        "relative_package": package_name[len(prefix):],
    }

    result = _export_one_blueprint(
        candidate
    )

    unreal.log(
        "[CodeXAI] Single graph export complete: {}".format(
            package_name
        )
    )

    unreal.log(
        "[CodeXAI] Authored graphs: {}".format(
            result["authored_graph_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Variables: {}".format(
            result["variable_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Nodes: {}".format(
            result["node_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Pins: {}".format(
            result["pin_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Connections: {}".format(
            result["connection_count"]
        )
    )

    if result["warnings"]:

        for warning in result["warnings"]:

            unreal.log_warning(
                "[CodeXAI] {}".format(
                    warning
                )
            )

    return result


# ============================================================================
# Public export
# ============================================================================


def export_graph_source(discovery_result):
    candidates = list(
        discovery_result[
            "assets"
        ]["full_graph"]
    )

    candidates.sort(
        key=lambda item: (
            item["package_name"].lower()
        )
    )

    unreal.log(
        "[CodeXAI] Exporting Blueprint graph source for {} assets..."
        .format(
            len(candidates)
        )
    )

    exported_count = 0

    errors = []
    warning_assets = []

    total_graphs = 0
    total_generated_graphs = 0

    total_nodes = 0
    total_pins = 0
    total_connections = 0
    total_variables = 0

    total_raw_bytes = 0

    for index, candidate in enumerate(
        candidates,
        start=1
    ):

        package_name = candidate[
            "package_name"
        ]

        try:

            result = _export_one_blueprint(
                candidate
            )

            exported_count += 1

            total_graphs += result[
                "authored_graph_count"
            ]

            total_generated_graphs += result[
                "generated_graph_count"
            ]

            total_nodes += result[
                "node_count"
            ]

            total_pins += result[
                "pin_count"
            ]

            total_connections += result[
                "connection_count"
            ]

            total_variables += result[
                "variable_count"
            ]

            total_raw_bytes += result[
                "raw_t3d_bytes"
            ]

            if result["warnings"]:

                warning_assets.append({
                    "package_name": package_name,
                    "warnings": result[
                        "warnings"
                    ],
                })

        except Exception as error:

            errors.append({
                "package_name": package_name,
                "error": str(error),
            })

            unreal.log_warning(
                "[CodeXAI] Graph export failed for {}: {}"
                .format(
                    package_name,
                    error
                )
            )

        if (
            index == 1
            or index % 25 == 0
            or index == len(candidates)
        ):

            unreal.log(
                "[CodeXAI] Graph progress: {}/{}"
                .format(
                    index,
                    len(candidates)
                )
            )

    return {
        "candidate_count": len(
            candidates
        ),

        "exported_count": exported_count,

        "error_count": len(
            errors
        ),

        "warning_asset_count": len(
            warning_assets
        ),

        "authored_graph_count": total_graphs,

        "generated_graph_count": (
            total_generated_graphs
        ),

        "variable_count": total_variables,

        "node_count": total_nodes,

        "pin_count": total_pins,

        "connection_count": (
            total_connections
        ),

        "raw_t3d_bytes": (
            total_raw_bytes
        ),

        "errors": errors,

        "warning_assets": (
            warning_assets
        ),
    }
