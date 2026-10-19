import json
import os
from datetime import datetime, timezone

import unreal

import CodeXAI
from CodeXAI import config
from CodeXAI import discovery
from CodeXAI import io_utils
from CodeXAI import metadata_exporter
from CodeXAI.graphs import graph_exporter
from CodeXAI.structural import structural_exporter
from CodeXAI import widget_exporter


# ============================================================================
# Discovery report
# ============================================================================


def _write_candidate_report(path, discovery_result):

    full_graph = discovery_result["assets"]["full_graph"]
    structural = discovery_result["assets"]["structural"]
    review = discovery_result["assets"]["review"]

    summary = discovery_result["summary"]

    lines = []

    lines.append("CodeX AI Context - Discovery Report")
    lines.append("=" * 80)
    lines.append("")

    lines.append(
        "Scanned:                 {}".format(
            summary.get("scanned", 0)
        )
    )

    lines.append(
        "Excluded by path:        {}".format(
            summary.get("excluded_by_path", 0)
        )
    )

    lines.append(
        "Excluded individually:   {}".format(
            summary.get(
                "excluded_individual_asset",
                0
            )
        )
    )

    lines.append(
        "Deprecated:              {}".format(
            summary.get("deprecated", 0)
        )
    )

    lines.append(
        "Ignored by class:        {}".format(
            summary.get("ignored_by_class", 0)
        )
    )

    lines.append(
        "Full graph:              {}".format(
            summary.get("full_graph", 0)
        )
    )

    lines.append(
        "Structural:              {}".format(
            summary.get("structural", 0)
        )
    )

    lines.append(
        "Manual review:           {}".format(
            summary.get("review", 0)
        )
    )

    lines.append(
        "Export candidates:       {}".format(
            summary.get("export_candidates", 0)
        )
    )

    lines.append("")
    lines.append("")

    lines.append(
        "FULL GRAPH ASSETS ({})".format(
            len(full_graph)
        )
    )

    lines.append("-" * 80)

    for asset in full_graph:

        lines.append(
            "{}    [{}]".format(
                asset["package_name"],
                asset["asset_class"]["name"]
            )
        )

    lines.append("")
    lines.append("")

    lines.append(
        "STRUCTURAL ASSETS ({})".format(
            len(structural)
        )
    )

    lines.append("-" * 80)

    for asset in structural:

        lines.append(
            "{}    [{}]".format(
                asset["package_name"],
                asset["asset_class"]["name"]
            )
        )

    lines.append("")
    lines.append("")

    lines.append(
        "REVIEW ({})".format(
            len(review)
        )
    )

    lines.append("-" * 80)

    if not review:

        lines.append(
            "No unclassified assets."
        )

    else:

        for asset in review:

            lines.append(
                "{}    [{}]".format(
                    asset["package_name"],
                    asset["asset_class"]["name"]
                )
            )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        file.write(
            "\n".join(lines)
        )


# ============================================================================
# Main
# ============================================================================


def run():

    unreal.log(
        "[CodeXAI] ========================================"
    )

    unreal.log(
        "[CodeXAI] CodeX AI Context Export"
    )

    unreal.log(
        "[CodeXAI] Exporter version: {}".format(
            CodeXAI.EXPORTER_VERSION
        )
    )

    unreal.log(
        "[CodeXAI] ========================================"
    )

    output_root = io_utils.ensure_output_root()

    unreal.log(
        "[CodeXAI] Output: {}".format(
            output_root
        )
    )

    if config.EXTERNAL_OUTPUT_ROOT:
        unreal.log(
            "[CodeXAI] Output mode: External repository"
        )
    else:
        unreal.log(
            "[CodeXAI] Output mode: Project Saved directory"
        )

    # ========================================================================
    # Stage 1 - Discovery
    # ========================================================================

    unreal.log(
        "[CodeXAI] Stage 1/4 - Discovery"
    )

    discovery_result = discovery.discover_assets()

    discovery_manifest = {
        "schema_version": 1,

        "exporter_version": CodeXAI.EXPORTER_VERSION,

        "generated_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "root_path": config.ROOT_PATH,

        "settings": {
            "excluded_paths": config.EXCLUDED_PATHS,

            "excluded_assets": sorted(
                config.EXCLUDED_ASSETS
            ),

            "deprecated_name_markers": list(
                config.DEPRECATED_NAME_MARKERS
            ),

            "full_graph_class_names": sorted(
                config.FULL_GRAPH_CLASS_NAMES
            ),

            "structural_class_names": sorted(
                config.STRUCTURAL_CLASS_NAMES
            ),

            "structural_name_prefixes": list(
                config.STRUCTURAL_NAME_PREFIXES
            ),
        },

        "discovery": discovery_result,
    }

    discovery_manifest_path = os.path.join(
        output_root,
        "discovery_manifest.json"
    )

    discovery_report_path = os.path.join(
        output_root,
        "discovery_candidates.txt"
    )

    io_utils.write_json(
        discovery_manifest_path,
        discovery_manifest
    )

    _write_candidate_report(
        discovery_report_path,
        discovery_result
    )

    # ========================================================================
    # Safety gate
    # ========================================================================

    review_count = discovery_result[
        "summary"
    ].get(
        "review",
        0
    )

    if review_count > 0:

        unreal.log_error(
            "[CodeXAI] Export stopped: {} unclassified assets remain.".format(
                review_count
            )
        )

        unreal.log_error(
            "[CodeXAI] Resolve REVIEW assets before metadata export."
        )

        return None

    # ========================================================================
    # Stage 2 - Architecture metadata
    # ========================================================================

    unreal.log(
        "[CodeXAI] Stage 2/4 - Architecture metadata"
    )

    metadata_summary = metadata_exporter.export_metadata(
        discovery_result
    )

    if metadata_summary["error_count"] > 0:

        unreal.log_error(
            "[CodeXAI] Export stopped: architecture metadata "
            "contains {} errors.".format(
                metadata_summary[
                    "error_count"
                ]
            )
        )

        unreal.log_error(
            "[CodeXAI] Resolve metadata errors before graph export."
        )

        return None

    # ========================================================================
    # Stage 3 - Blueprint graph source
    # ========================================================================

    unreal.log(
        "[CodeXAI] Stage 3/4 - Blueprint graph source"
    )

    graph_summary = graph_exporter.export_graph_source(
        discovery_result
    )

    # ========================================================================
    # Stage 4 - Structural source
    # ========================================================================

    unreal.log(
        "[CodeXAI] Stage 4/4 - Structural source"
    )

    structural_summary = (
        structural_exporter.export_structural_source(
            discovery_result
        )
    )

    #
========================================================================
    # Stage 5 - Widget Blueprint Designer
    #
========================================================================

    unreal.log(
        "[CodeXAI] Stage 5/5 - Widget Designer"
    )

    widget_summary = widget_exporter.export_widget_source(
        discovery_result
    )


    # ========================================================================
    # Final manifest
    # ========================================================================

    try:
        engine_version = (
            unreal.BlueprintEditorLibrary.get_current_engine_version()
        )
    except Exception:
        engine_version = "Unknown"

    export_manifest = {
        "schema_version": 1,

        "exporter_version": CodeXAI.EXPORTER_VERSION,

        "generated_utc": datetime.now(
            timezone.utc
        ).isoformat(),

        "engine_version": engine_version,

        "root_path": config.ROOT_PATH,

        "discovery_summary": discovery_result[
            "summary"
        ],

        "metadata_export": metadata_summary,

        "graph_export": graph_summary,

        "structural_export": structural_summary,

        "widget_export": widget_summary,
    }

    export_manifest_path = os.path.join(
        output_root,
        "export_manifest.json"
    )

    io_utils.write_json(
        export_manifest_path,
        export_manifest
    )

    # ========================================================================
    # Final log
    # ========================================================================

    unreal.log(
        "[CodeXAI] ----------------------------------------"
    )

    unreal.log(
        "[CodeXAI] Blueprint graph source"
    )

    unreal.log(
        "[CodeXAI] Graph candidates: {}".format(
            graph_summary["candidate_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Graph assets exported: {}".format(
            graph_summary["exported_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Authored graphs: {}".format(
            graph_summary["authored_graph_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Generated graphs: {}".format(
            graph_summary["generated_graph_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Variables: {}".format(
            graph_summary["variable_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Nodes: {}".format(
            graph_summary["node_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Pins: {}".format(
            graph_summary["pin_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Connections: {}".format(
            graph_summary["connection_count"]
        )
    )

    unreal.log(
        "[CodeXAI] Raw T3D bytes: {}".format(
            graph_summary["raw_t3d_bytes"]
        )
    )

    if graph_summary["warning_asset_count"] > 0:
        unreal.log_warning(
            "[CodeXAI] Graph assets with warnings: {}".format(
                graph_summary[
                    "warning_asset_count"
                ]
            )
        )

    else:
        unreal.log(
            "[CodeXAI] Graph assets with warnings: 0"
        )


    if graph_summary["error_count"] > 0:
        unreal.log_warning(
            "[CodeXAI] Graph export errors: {}".format(
                graph_summary[
                    "error_count"
                ]
            )
        )

    else:
        unreal.log(
            "[CodeXAI] Graph export errors: 0"
        )

    unreal.log(
        "[CodeXAI] ----------------------------------------"
    )

    unreal.log(
        "[CodeXAI] Structural source"
    )

    unreal.log(
        "[CodeXAI] Structural candidates: {}".format(
            structural_summary[
                "candidate_count"
            ]
        )
    )

    unreal.log(
        "[CodeXAI] Structural assets exported: {}".format(
            structural_summary[
                "exported_count"
            ]
        )
    )

    unreal.log(
        "[CodeXAI] Raw structural T3D bytes: {}".format(
            structural_summary[
                "raw_t3d_bytes"
            ]
        )
    )

    unreal.log(
        "[CodeXAI] Serializer counts: {}".format(
            structural_summary[
                "serializer_counts"
            ]
        )
    )

    unreal.log(
        "[CodeXAI] Structural class counts: {}".format(
            structural_summary[
                "class_counts"
            ]
        )
    )

    if structural_summary[
        "warning_asset_count"
    ] > 0:

        unreal.log_warning(
            "[CodeXAI] Structural assets with warnings: {}"
            .format(
                structural_summary[
                    "warning_asset_count"
                ]
            )
        )

    else:

        unreal.log(
            "[CodeXAI] Structural assets with warnings: 0"
        )


    if structural_summary[
        "error_count"
    ] > 0:

        unreal.log_warning(
            "[CodeXAI] Structural export errors: {}"
            .format(
                structural_summary[
                    "error_count"
                ]
            )
        )

    else:

        unreal.log(
            "[CodeXAI] Structural export errors: 0"
        )


    unreal.log(
        "[CodeXAI] CodeX AI context export complete"
    )

    unreal.log(
        "[CodeXAI] ========================================"
    )

    return export_manifest_path


if __name__ == "__main__":
    run()