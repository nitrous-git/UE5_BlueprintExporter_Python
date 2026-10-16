"""Standalone audit: same discovery report as the existing full exporter."""

import os
from datetime import datetime, timezone

import unreal
from CodeXAI import config, discovery, io_utils
from CodeXAI import export_context
from CodeXAI import EXPORTER_VERSION


def run():
    """Write audit reports only. Do not modify or delete existing exports."""
    output_root = io_utils.ensure_output_root()
    unreal.log("[UE5_BP_Exporter] Audit Project: {}".format(config.ROOT_PATH))

    result = discovery.discover_assets()
    manifest = {
        "schema_version": 1,
        "exporter_version": EXPORTER_VERSION,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "root_path": config.ROOT_PATH,
        "settings": {
            "excluded_paths": config.EXCLUDED_PATHS,
            "excluded_assets": sorted(config.EXCLUDED_ASSETS),
            "deprecated_name_markers": list(config.DEPRECATED_NAME_MARKERS),
            "full_graph_class_names": sorted(config.FULL_GRAPH_CLASS_NAMES),
            "structural_class_names": sorted(config.STRUCTURAL_CLASS_NAMES),
            "structural_name_prefixes": list(config.STRUCTURAL_NAME_PREFIXES),
        },
        "discovery": result,
    }

    manifest_path = os.path.join(output_root, "discovery_manifest.json")
    report_path = os.path.join(output_root, "discovery_candidates.txt")
    io_utils.write_json(manifest_path, manifest)
    export_context._write_candidate_report(report_path, result)

    summary = result["summary"]
    unreal.log(
        "[UE5_BP_Exporter] Audit complete: {} graph, {} structural, {} review."
        .format(
            summary.get("full_graph", 0),
            summary.get("structural", 0),
            summary.get("review", 0),
        )
    )
    unreal.log("[UE5_BP_Exporter] Discovery report: {}".format(report_path))
    return manifest_path
