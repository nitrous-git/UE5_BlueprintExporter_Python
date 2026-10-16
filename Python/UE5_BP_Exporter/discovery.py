"""Asset Registry discovery/classification; safe to run without full export."""

from collections import Counter

import unreal
from CodeXAI import config


def _normalize_unreal_path(path):
    return str(path).replace("\\", "/").rstrip("/")


def _is_same_or_child_path(path, parent_path):
    path = _normalize_unreal_path(path)
    parent_path = _normalize_unreal_path(parent_path)
    return path == parent_path or path.startswith(parent_path + "/")


def _get_excluded_path(package_path):
    for excluded in config.EXCLUDED_PATHS:
        if _is_same_or_child_path(package_path, excluded):
            return excluded
    return None


def _get_asset_class_info(asset_data):
    """Return native /Script package and class name."""
    try:
        return (
            str(asset_data.asset_class_path.package_name),
            str(asset_data.asset_class_path.asset_name),
        )
    except Exception:
        raw = str(asset_data.asset_class_path)
        return tuple(raw.rsplit(".", 1)) if "." in raw else ("", raw)


def _is_deprecated_asset(asset_name):
    return any(
        marker and marker.lower() in asset_name.lower()
        for marker in config.DEPRECATED_NAME_MARKERS
    )


def _relative_package_path(package_name):
    root = _normalize_unreal_path(config.ROOT_PATH)
    package_name = _normalize_unreal_path(package_name)
    if package_name.startswith(root + "/"):
        return package_name[len(root) + 1:]
    return package_name.lstrip("/")


def _is_excluded_asset(package_name):
    return _normalize_unreal_path(package_name) in {
        _normalize_unreal_path(entry) for entry in config.EXCLUDED_ASSETS
    }


def classify_asset(asset_name, class_name):
    """Unknown asset types always go to REVIEW for a deliberate decision."""
    if class_name in config.FULL_GRAPH_CLASS_NAMES:
        return "FULL_GRAPH", "Logic-bearing Blueprint class"
    if class_name in config.STRUCTURAL_CLASS_NAMES:
        return "STRUCTURAL", "Known structural asset class"
    if class_name in config.IGNORE_CLASS_NAMES:
        return "IGNORE", "Known non-code content class"
    for prefix in config.STRUCTURAL_NAME_PREFIXES:
        if asset_name.startswith(prefix):
            return "STRUCTURAL", "Included by structural naming convention"
    return "REVIEW", "Unknown asset class - manual review required"


def discover_assets():
    """Enumerate configured content root; read-only with respect to assets."""
    root = _normalize_unreal_path(config.ROOT_PATH)
    if not root.startswith("/Game") or (root != "/Game" and not root.startswith("/Game/")):
        raise ValueError("ROOT_PATH must be /Game or a path under /Game: {}".format(root))

    unreal.log("[UE5_BP_Exporter] Scanning {}".format(root))
    registry = unreal.AssetRegistryHelpers.get_asset_registry()
    assets = registry.get_assets_by_path(
        package_path=unreal.Name(root),
        recursive=True,
        include_only_on_disk_assets=True,
    ) or []

    results = {"full_graph": [], "structural": [], "review": []}
    counters = Counter()
    all_classes = Counter()
    review_classes = Counter()
    excluded_paths = Counter()
    counters["scanned"] = len(assets)

    for data in assets:
        asset_name = str(data.asset_name)
        package_name = str(data.package_name)
        package_path = str(data.package_path)
        class_package, class_name = _get_asset_class_info(data)
        all_classes[class_name] += 1

        excluded_path = _get_excluded_path(package_path)
        if excluded_path is not None:
            counters["excluded_by_path"] += 1
            excluded_paths[excluded_path] += 1
            continue
        if _is_deprecated_asset(asset_name):
            counters["deprecated"] += 1
            continue
        if _is_excluded_asset(package_name):
            counters["excluded_individual_asset"] += 1
            continue

        category, reason = classify_asset(asset_name, class_name)
        if category == "IGNORE":
            counters["ignored_by_class"] += 1
            continue

        relative_package = _relative_package_path(package_name)
        entry = {
            "asset_name": asset_name,
            "package_name": package_name,
            "package_path": package_path,
            "object_path": "{}.{}".format(package_name, asset_name),
            "relative_package": relative_package,
            "asset_class": {"package": class_package, "name": class_name},
            "category": category,
            "classification_reason": reason,
            "planned_export_path": (
                config.MIRROR_FOLDER_NAME.rstrip("/") + "/" + relative_package
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
            review_classes[class_name] += 1
            results["review"].append(entry)

    if config.SORT_RESULTS:
        for category_assets in results.values():
            category_assets.sort(key=lambda item: item["package_name"].lower())

    # Export manifests from previous versions expect these key names.
    counters["export_candidates"] = counters["full_graph"] + counters["structural"]
    return {
        "summary": dict(counters),
        "class_breakdown": dict(sorted(all_classes.items())),
        "review_class_breakdown": dict(sorted(review_classes.items())),
        "excluded_path_breakdown": dict(sorted(excluded_paths.items())),
        "assets": results,
    }
