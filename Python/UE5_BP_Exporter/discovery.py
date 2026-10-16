from collections import Counter

import unreal

from CodeXAI import config


# ============================================================================
# Path helpers
# ============================================================================


def _normalize_unreal_path(path):
    """
    Normalize an Unreal package path for reliable comparisons.
    """

    path = str(path).replace("\\", "/").rstrip("/")

    return path


def _is_same_or_child_path(path, parent_path):
    """
    Returns True when:

        path == parent_path

    or:

        path is below parent_path

    Prevents false matches such as:

        /Inventory
        /InventorySystemRefactor
    """

    path = _normalize_unreal_path(path)
    parent_path = _normalize_unreal_path(parent_path)

    return (
        path == parent_path
        or path.startswith(parent_path + "/")
    )


def _get_excluded_path(package_path):
    """
    Return the matching excluded root, or None.
    """

    for excluded_path in config.EXCLUDED_PATHS:

        if _is_same_or_child_path(
            package_path,
            excluded_path
        ):
            return excluded_path

    return None


# ============================================================================
# Asset helpers
# ============================================================================


def _get_asset_class_info(asset_data):
    """
    Return:

        class_package
        class_name

    Example:

        /Script/Engine
        Blueprint
    """

    try:

        class_path = asset_data.asset_class_path

        class_package = str(class_path.package_name)
        class_name = str(class_path.asset_name)

        return class_package, class_name

    except Exception:

        # Defensive fallback in case an unusual asset exposes the path
        # differently through Python.

        raw = str(asset_data.asset_class_path)

        if "." in raw:
            class_package, class_name = raw.rsplit(".", 1)
            return class_package, class_name

        return "", raw


def _is_deprecated_asset(asset_name):
    """
    CodeX convention:

        _dep

    anywhere in the asset name means deprecated / old system.

    This deliberately also catches Unreal-generated/redirector names such as:

        AC_InventoryComponent_dep_C
        Default__AC_InventoryComponent_dep_C
    """

    name_lower = asset_name.lower()

    for marker in config.DEPRECATED_NAME_MARKERS:

        if marker.lower() in name_lower:
            return True

    return False


def _relative_package_path(package_name):
    """
    Convert:

        /Game/CodeX_Restruct/Frameworks/PlayerFramework/Core/BP_PlayerBase

    into:

        Frameworks/PlayerFramework/Core/BP_PlayerBase
    """

    root = _normalize_unreal_path(config.ROOT_PATH)
    package_name = _normalize_unreal_path(package_name)

    root_prefix = root + "/"

    if package_name.startswith(root_prefix):
        return package_name[len(root_prefix):]

    return package_name.lstrip("/")


def _is_excluded_asset(package_name):
    """
    Return True when this exact asset package is explicitly excluded.

    Unlike EXCLUDED_PATHS, this does NOT exclude children or neighboring
    assets.
    """

    package_name = _normalize_unreal_path(package_name)

    return package_name in {
        _normalize_unreal_path(path)
        for path in config.EXCLUDED_ASSETS
    }

# ============================================================================
# Classification
# ============================================================================


def classify_asset(asset_name, class_name):
    """
    Returns:

        category
        reason

    Categories:

        FULL_GRAPH
        STRUCTURAL
        IGNORE
        REVIEW
    """

    # ----------------------------------------------------------------------
    # Full executable Blueprint graph
    # ----------------------------------------------------------------------

    if class_name in config.FULL_GRAPH_CLASS_NAMES:

        return (
            "FULL_GRAPH",
            "Logic-bearing Blueprint class"
        )

    # ----------------------------------------------------------------------
    # Known structural Unreal assets
    # ----------------------------------------------------------------------

    if class_name in config.STRUCTURAL_CLASS_NAMES:

        return (
            "STRUCTURAL",
            "Known structural asset class"
        )

    # ----------------------------------------------------------------------
    # Known content / presentation assets
    # ----------------------------------------------------------------------

    if class_name in config.IGNORE_CLASS_NAMES:

        return (
            "IGNORE",
            "Known non-code content class"
        )

    # ----------------------------------------------------------------------
    # Secondary naming safety net
    #
    # Useful especially for Data Asset instances whose class may be a
    # project-defined Blueprint-generated class.
    # ----------------------------------------------------------------------

    for prefix in config.STRUCTURAL_NAME_PREFIXES:

        if asset_name.startswith(prefix):

            return (
                "STRUCTURAL",
                "Included by CodeX structural naming convention"
            )

    # ----------------------------------------------------------------------
    # IMPORTANT:
    #
    # Unknown != ignored.
    #
    # We deliberately surface unknown asset types for manual review.
    # ----------------------------------------------------------------------

    return (
        "REVIEW",
        "Unknown asset class - manual review required"
    )


# ============================================================================
# Discovery
# ============================================================================


def discover_assets():
    """
    Scan the CodeX project root and classify relevant assets.

    This function is READ-ONLY with respect to Unreal assets.
    """

    unreal.log(
        "[CodeXAI] Scanning {}".format(config.ROOT_PATH)
    )

    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

    assets = asset_registry.get_assets_by_path(
        package_path=unreal.Name(config.ROOT_PATH),
        recursive=True,
        include_only_on_disk_assets=True
    )

    if assets is None:
        assets = []

    results = {
        "full_graph": [],
        "structural": [],
        "review": [],
    }

    counters = Counter()
    class_counter = Counter()
    review_class_counter = Counter()
    excluded_path_counter = Counter()

    counters["scanned"] = len(assets)

    for asset_data in assets:

        asset_name = str(asset_data.asset_name)
        package_name = str(asset_data.package_name)
        package_path = str(asset_data.package_path)

        class_package, class_name = _get_asset_class_info(
            asset_data
        )

        class_counter[class_name] += 1

        # ------------------------------------------------------------------
        # Path exclusion
        # ------------------------------------------------------------------

        excluded_path = _get_excluded_path(package_path)

        if excluded_path is not None:
            counters["excluded_by_path"] += 1
            excluded_path_counter[excluded_path] += 1
            continue

        # ------------------------------------------------------------------
        # Deprecated asset exclusion
        # ------------------------------------------------------------------

        if _is_deprecated_asset(asset_name):
            counters["deprecated"] += 1
            continue

        # ------------------------------------------------------------------
        # Exact asset exclusion
        # ------------------------------------------------------------------

        if _is_excluded_asset(package_name):
            counters["excluded_individual_asset"] += 1
            continue

        # ------------------------------------------------------------------
        # Classification
        # ------------------------------------------------------------------

        category, reason = classify_asset(
            asset_name,
            class_name
        )

        if category == "IGNORE":

            counters["ignored_by_class"] += 1

            continue

        relative_package = _relative_package_path(
            package_name
        )

        entry = {
            "asset_name": asset_name,

            "package_name": package_name,
            "package_path": package_path,

            "object_path": "{}.{}".format(
                package_name,
                asset_name
            ),

            "relative_package": relative_package,

            "asset_class": {
                "package": class_package,
                "name": class_name,
            },

            "category": category,
            "classification_reason": reason,

            # Commit 2+ will materialize the exported asset here.
            "planned_export_path": (
                "CodeX_Restruct/" + relative_package
            ),
        }

        if category == "FULL_GRAPH":

            counters["full_graph"] += 1
            results["full_graph"].append(entry)

        elif category == "STRUCTURAL":

            counters["structural"] += 1
            results["structural"].append(entry)

        else:

            counters["review"] += 1
            review_class_counter[class_name] += 1
            results["review"].append(entry)

    # ----------------------------------------------------------------------
    # Stable ordering is important for future Git diffs.
    # ----------------------------------------------------------------------

    if config.SORT_RESULTS:

        for category_assets in results.values():

            category_assets.sort(
                key=lambda asset: asset["package_name"].lower()
            )

    counters["export_candidates"] = (
        counters["full_graph"]
        + counters["structural"]
    )

    return {
        "summary": dict(counters),

        "class_breakdown": dict(
            sorted(class_counter.items())
        ),

        "review_class_breakdown": dict(
            sorted(review_class_counter.items())
        ),

        "excluded_path_breakdown": dict(
            sorted(excluded_path_counter.items())
        ),

        "assets": results,
    }