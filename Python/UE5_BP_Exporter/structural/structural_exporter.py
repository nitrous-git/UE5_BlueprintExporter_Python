import json
import os

import unreal

from CodeXAI import config
from CodeXAI import io_utils
from CodeXAI.graphs import raw_exporter

from CodeXAI.structural import serializers
from CodeXAI.structural import t3d_object_parser


# ============================================================================
# Helpers
# ============================================================================


def _read_json(filename):
    with open(
        filename,
        "r",
        encoding="utf-8"
    ) as file:

        return json.load(
            file
        )


def _asset_identity(
    asset,
    candidate
):
    return {
        "name": asset.get_name(),
        "package_name": candidate[
            "package_name"
        ],
        "relative_package": candidate[
            "relative_package"
        ],
        "class": asset.get_class().get_name(),
        "object_path": asset.get_path_name(),
    }


def _update_asset_json(
    asset_directory,
    structural_document
):
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

    document["structural_source"] = {
        "file": "structural.json",

        "serializer": structural_document[
            "serializer"
        ],

        "raw_t3d": (
            "_raw/structural.t3d"
            if structural_document[
                "raw"
            ]["t3d_exported"]
            else None
        ),
    }

    io_utils.write_json(
        asset_json_path,
        document
    )


def _export_raw_t3d(
    asset,
    raw_filename
):
    result = (
        raw_exporter.export_object_t3d(
            asset,
            raw_filename
        )
    )

    if not result.get(
        "success",
        False
    ):
        return (
            result,
            {
                "encoding": None,
                "roots": [],
            }
        )

    parsed = (
        t3d_object_parser.parse_file(
            raw_filename
        )
    )

    return result, parsed


# ============================================================================
# One asset
# ============================================================================


def _export_one(candidate):
    package_name = candidate[
        "package_name"
    ]

    asset = unreal.EditorAssetLibrary.load_asset(
        package_name
    )

    if asset is None:
        raise RuntimeError(
            "Unable to load structural asset: {}".format(
                package_name
            )
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

    os.makedirs(
        raw_directory,
        exist_ok=True
    )

    raw_filename = os.path.join(
        raw_directory,
        "structural.t3d"
    )

    warnings = []

    raw_result, raw_tree = (
        _export_raw_t3d(
            asset,
            raw_filename
        )
    )

    if not raw_result.get(
        "success",
        False
    ):

        warnings.append(
            "Raw T3D export failed: {}".format(
                raw_result.get(
                    "errors",
                    []
                )
            )
        )

    elif not raw_tree["roots"]:

        warnings.append(
            "Raw T3D exported successfully but the generic object-tree "
            "parser found no root objects."
        )

    specialized = serializers.serialize(
        asset,
        raw_tree["roots"]
    )

    structural_document = {
        "schema_version": 1,

        "asset": _asset_identity(
            asset,
            candidate
        ),

        "serializer": specialized[
            "serializer"
        ],

        "data": specialized[
            "data"
        ],

        # Generic normalized representation of Unreal's own text export.
        # This is intentionally retained even when a class-specific serializer
        # exists so we do not lose project-specific or engine-specific fields.
        "raw_object_tree": raw_tree[
            "roots"
        ],

        "raw": {
            "t3d_exported": bool(
                raw_result.get(
                    "success",
                    False
                )
            ),

            "t3d_file": (
                "_raw/structural.t3d"
                if raw_result.get(
                    "success",
                    False
                )
                else None
            ),

            "encoding": raw_tree[
                "encoding"
            ],

            "size_bytes": raw_result.get(
                "file_size_bytes",
                0
            ),
        },

        "warnings": warnings,
    }

    output_path = os.path.join(
        asset_directory,
        "structural.json"
    )

    io_utils.write_json(
        output_path,
        structural_document
    )

    _update_asset_json(
        asset_directory,
        structural_document
    )

    return {
        "package_name": package_name,

        "asset_class": asset.get_class().get_name(),

        "serializer": structural_document[
            "serializer"
        ],

        "raw_t3d_bytes": structural_document[
            "raw"
        ]["size_bytes"],

        "warning_count": len(
            warnings
        ),

        "warnings": warnings,
    }


# ============================================================================
# Single-asset validation
# ============================================================================


def export_single(package_name):
    root = config.ROOT_PATH.rstrip("/")
    package_name = str(
        package_name
    ).rstrip("/")

    prefix = root + "/"

    if not package_name.startswith(
        prefix
    ):
        raise RuntimeError(
            "Structural asset is outside configured CodeX root: {}"
            .format(
                package_name
            )
        )

    result = _export_one({
        "package_name": package_name,
        "relative_package": package_name[
            len(prefix):
        ],
    })

    unreal.log(
        "[CodeXAI] Single structural export complete: {}"
        .format(
            package_name
        )
    )

    unreal.log(
        "[CodeXAI] Serializer: {}".format(
            result["serializer"]
        )
    )

    unreal.log(
        "[CodeXAI] Raw T3D bytes: {}".format(
            result["raw_t3d_bytes"]
        )
    )

    unreal.log(
        "[CodeXAI] Warnings: {}".format(
            result["warning_count"]
        )
    )

    return result


# ============================================================================
# Public export
# ============================================================================


def export_structural_source(
    discovery_result
):
    candidates = list(
        discovery_result[
            "assets"
        ]["structural"]
    )

    candidates.sort(
        key=lambda item: (
            item["package_name"].lower()
        )
    )

    unreal.log(
        "[CodeXAI] Exporting structural source for {} assets..."
        .format(
            len(candidates)
        )
    )

    exported_count = 0

    errors = []
    warning_assets = []

    serializer_counts = {}
    class_counts = {}

    total_raw_bytes = 0

    for index, candidate in enumerate(
        candidates,
        start=1
    ):

        package_name = candidate[
            "package_name"
        ]

        try:

            result = _export_one(
                candidate
            )

            exported_count += 1

            serializer_name = result[
                "serializer"
            ]

            serializer_counts[
                serializer_name
            ] = (
                serializer_counts.get(
                    serializer_name,
                    0
                )
                + 1
            )

            asset_class = result[
                "asset_class"
            ]

            class_counts[
                asset_class
            ] = (
                class_counts.get(
                    asset_class,
                    0
                )
                + 1
            )

            total_raw_bytes += result[
                "raw_t3d_bytes"
            ]

            if result[
                "warning_count"
            ] > 0:

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
                "[CodeXAI] Structural export failed for {}: {}"
                .format(
                    package_name,
                    error
                )
            )

        if (
            index == 1
            or index % 20 == 0
            or index == len(candidates)
        ):

            unreal.log(
                "[CodeXAI] Structural progress: {}/{}"
                .format(
                    index,
                    len(candidates)
                )
            )

    return {
        "candidate_count": len(
            candidates
        ),

        "exported_count": (
            exported_count
        ),

        "error_count": len(
            errors
        ),

        "warning_asset_count": len(
            warning_assets
        ),

        "serializer_counts": dict(
            sorted(
                serializer_counts.items()
            )
        ),

        "class_counts": dict(
            sorted(
                class_counts.items()
            )
        ),

        "raw_t3d_bytes": (
            total_raw_bytes
        ),

        "errors": errors,

        "warning_assets": (
            warning_assets
        ),
    }
