import os

import unreal

from CodeXAI import io_utils


# ============================================================================
# Safe serialization helpers
# ============================================================================


def _stringify(value):
    """
    Convert common Unreal/Python values into deterministic readable strings.
    """

    if value is None:
        return None

    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return value

    if isinstance(value, str):
        return value

    try:
        if isinstance(value, unreal.Name):
            return str(value)
    except Exception:
        pass

    try:
        if isinstance(value, unreal.Text):
            return str(value)
    except Exception:
        pass

    # Unreal UObject
    try:
        if isinstance(value, unreal.Object):
            return value.get_path_name()
    except Exception:
        pass

    # Unreal structs often expose a stable export_text().
    try:
        return value.export_text()
    except Exception:
        pass

    return str(value)


def _safe_editor_property(obj, property_name):
    """
    Read-only property access.

    UBlueprint's Python surface differs somewhat between engine versions.
    We therefore try get_editor_property first and normal Python attribute
    access second.

    Returns:
        (success, value)
    """

    if obj is None:
        return False, None

    try:
        return True, obj.get_editor_property(property_name)
    except Exception:
        pass

    try:
        return True, getattr(obj, property_name)
    except Exception:
        return False, None


def _object_identity(obj):
    if obj is None:
        return None

    result = {}

    try:
        result["name"] = obj.get_name()
    except Exception:
        result["name"] = str(obj)

    try:
        result["path"] = obj.get_path_name()
    except Exception:
        result["path"] = None

    try:
        result["class"] = obj.get_class().get_name()
    except Exception:
        result["class"] = None

    return result


# ============================================================================
# Asset Registry helpers
# ============================================================================


def _make_dependency_options():
    """
    Hard + soft package references are useful for architecture.

    Searchable-name and management references are not needed for this pass.
    """

    return unreal.AssetRegistryDependencyOptions(
        include_soft_package_references=True,
        include_hard_package_references=True,
        include_searchable_names=False,
        include_soft_management_references=False,
        include_hard_management_references=False
    )


def _find_asset_data(registry, package_name, asset_name):
    """
    Resolve a discovery-manifest entry back to Unreal AssetData.
    """

    assets = registry.get_assets_by_package_name(
        unreal.Name(package_name),
        include_only_on_disk_assets=False
    )

    if not assets:
        return None

    for asset_data in assets:
        if str(asset_data.asset_name) == asset_name:
            return asset_data

    # Most packages contain one primary asset.
    # Use it as a defensive fallback.
    return assets[0]


def _registry_tag(asset_data, tag_name):
    if asset_data is None:
        return None

    try:
        value = unreal.AssetRegistryHelpers.get_tag_value(
            asset_data,
            unreal.Name(tag_name)
        )

        if value:
            return str(value)

    except Exception:
        pass

    try:
        value = asset_data.get_tag_value(
            unreal.Name(tag_name)
        )

        if value:
            return str(value)

    except Exception:
        pass

    return None


def _get_architecture_references(
    registry,
    package_name,
    candidate_packages,
    dependency_options
):
    """
    Keep detailed dependency information ONLY for assets that are themselves
    part of our 254-asset CodeX architecture.

    All presentation/content references are represented only as counts.
    """

    dependencies = registry.get_dependencies(
        unreal.Name(package_name),
        dependency_options
    ) or []

    referencers = registry.get_referencers(
        unreal.Name(package_name),
        dependency_options
    ) or []

    dependency_names = sorted({
        str(item)
        for item in dependencies
    })

    referencer_names = sorted({
        str(item)
        for item in referencers
    })

    architecture_dependencies = [
        path
        for path in dependency_names
        if path in candidate_packages
    ]

    architecture_referencers = [
        path
        for path in referencer_names
        if path in candidate_packages
    ]

    non_architecture_dependencies = [
        path
        for path in dependency_names
        if path not in candidate_packages
    ]

    non_architecture_referencers = [
        path
        for path in referencer_names
        if path not in candidate_packages
    ]

    return {
        "dependencies": architecture_dependencies,
        "referencers": architecture_referencers,

        # Useful diagnostic without polluting asset.json with thousands of
        # materials, textures, animations, meshes, etc.
        "non_architecture_dependency_count": len(
            non_architecture_dependencies
        ),

        "non_architecture_referencer_count": len(
            non_architecture_referencers
        ),
    }


# ============================================================================
# Blueprint metadata
# ============================================================================


def _graph_names(blueprint, property_name):
    success, graphs = _safe_editor_property(
        blueprint,
        property_name
    )

    if not success or not graphs:
        return []

    results = []

    for graph in graphs:

        if graph is None:
            continue

        try:
            graph_name = graph.get_name()
        except Exception:
            graph_name = str(graph)

        results.append(graph_name)

    return sorted(set(results))


def _extract_graph_summary(blueprint):
    """
    UE 5.6 Python exposes direct lookup of the primary EventGraph, but does not
    provide the comprehensive graph-list API available in newer engine
    versions.

    Complete graph discovery is deferred to Commit 3 text serialization.
    """

    result = {
        "primary_event_graph": None,

        "complete_graph_list": "deferred_to_commit_3"
    }

    try:
        event_graph = unreal.BlueprintEditorLibrary.find_event_graph(
            blueprint
        )

        if event_graph is not None:
            result["primary_event_graph"] = (
                event_graph.get_name()
            )

    except Exception:
        pass

    return result


def _extract_variables(blueprint, warnings):
    """
    UE 5.6 does not expose UBlueprint.new_variables through the Python API.

    Full Blueprint variable definitions are therefore deferred to the raw
    Blueprint graph/text extraction performed in Commit 3.
    """

    return []


def _extract_interfaces(blueprint):
    success, interface_descriptions = _safe_editor_property(
        blueprint,
        "implemented_interfaces"
    )

    if not success or not interface_descriptions:
        return []

    results = []

    for description in interface_descriptions:

        success, interface_class = _safe_editor_property(
            description,
            "interface"
        )

        if success and interface_class is not None:

            try:
                results.append(
                    interface_class.get_path_name()
                )
            except Exception:
                results.append(
                    str(interface_class)
                )

        else:

            try:
                results.append(
                    description.export_text()
                )
            except Exception:
                results.append(
                    str(description)
                )

    return sorted(set(results))


def _component_parent_name(
    data,
    subobject_library
):
    try:
        parent_handle = subobject_library.get_parent_handle(
            data
        )

        parent_data = subobject_library.get_data(
            parent_handle
        )

        if parent_data is None:
            return None

        try:
            variable_name = subobject_library.get_variable_name(
                parent_data
            )

            variable_name = str(variable_name)

            if variable_name and variable_name != "None":
                return variable_name

        except Exception:
            pass

        try:
            return str(
                subobject_library.get_display_name(
                    parent_data
                )
            )
        except Exception:
            return None

    except Exception:
        return None


def _is_actor_blueprint(blueprint):
    """
    Return True only when this Blueprint generates an Actor-derived class.

    SubobjectDataSubsystem's Blueprint gathering path is useful for Actor
    Blueprints, but calling it for ActorComponents, Widgets, AnimInstances,
    DataAssets, interfaces, etc. produces noisy editor warnings.
    """

    try:
        generated_class = unreal.BlueprintEditorLibrary.generated_class(
            blueprint
        )

        if generated_class is None:
            return False

        class_default_object = unreal.get_default_object(
            generated_class
        )

        return isinstance(
            class_default_object,
            unreal.Actor
        )

    except Exception:
        return False

def _extract_components(blueprint, warnings):
    """
    Read Actor Blueprint subobjects/components through SubobjectDataSubsystem.

    Non-Actor Blueprints intentionally have no Actor component hierarchy and
    must never be passed to k2_gather_subobject_data_for_blueprint().
    """

    # IMPORTANT:
    # WidgetBlueprints, ActorComponent Blueprints, AnimBlueprints,
    # DataAsset Blueprints, Blueprint Interfaces, etc. are FULL_GRAPH assets
    # but are NOT Actor Blueprints.
    #
    # UE 5.6's SubobjectDataSubsystem logs:
    #
    #   "Could not gather subobject data,
    #    the given context was not an actor!"
    #
    # if we pass those Blueprints to it.
    if not _is_actor_blueprint(blueprint):
        return []

    try:
        subsystem = unreal.get_engine_subsystem(
            unreal.SubobjectDataSubsystem
        )

        if subsystem is None:
            warnings.append(
                "SubobjectDataSubsystem is unavailable."
            )
            return []

        handles = subsystem.k2_gather_subobject_data_for_blueprint(
            blueprint
        )

    except Exception as error:

        warnings.append(
            "Unable to gather Blueprint subobjects: {}".format(
                error
            )
        )

        return []

    library = unreal.SubobjectDataBlueprintFunctionLibrary

    results = []

    library = unreal.SubobjectDataBlueprintFunctionLibrary

    results = []

    for handle in handles:

        try:
            data = library.get_data(handle)

            if data is None:
                continue

            # Ignore the Actor/root and any other non-component subobjects
            # BEFORE attempting Blueprint object resolution.

            try:
                if not library.is_component(data):
                    continue
            except Exception:
                continue

            # --------------------------------------------------------------
            # Now we know this SubobjectData actually represents a component.
            # --------------------------------------------------------------

            obj = None

            # Prefer the Blueprint-aware accessor.
            try:
                obj = library.get_object_for_blueprint(
                    data,
                    blueprint
                )
            except Exception:
                pass

            if obj is None:
                try:
                    obj = library.get_object(data)
                except Exception:
                    pass

            if obj is None:
                continue

            try:
                variable_name = str(
                    library.get_variable_name(data)
                )
            except Exception:
                variable_name = None

            if not variable_name or variable_name == "None":

                try:
                    variable_name = str(
                        library.get_display_name(data)
                    )
                except Exception:
                    variable_name = obj.get_name()

            is_scene_component = bool(
                library.is_scene_component(data)
            )

            is_root_component = (
                bool(
                    library.is_root_component(data)
                )
                if is_scene_component
                else False
            )

            component = {
                "name": variable_name,

                "class": obj.get_class().get_name(),

                "parent": _component_parent_name(
                    data,
                    library
                ),

                "inherited": bool(
                    library.is_inherited_component(data)
                ),

                "native": bool(
                    library.is_native_component(data)
                ),

                "root_component": is_root_component,

                "scene_component": is_scene_component,
            }

            try:
                component["template_path"] = obj.get_path_name()
            except Exception:
                component["template_path"] = None

            results.append(component)

        except Exception as error:

            warnings.append(
                "Unable to inspect one Blueprint component: {}".format(
                    error
                )
            )

    # De-duplicate in case the subsystem surfaces the same component through
    # multiple handles.
    deduplicated = {}

    for item in results:
        key = (
            item.get("name"),
            item.get("class")
        )

        deduplicated[key] = item

    results = list(
        deduplicated.values()
    )

    results.sort(
        key=lambda item: str(
            item.get("name", "")
        ).lower()
    )

    return results


def _extract_blueprint_metadata(
    asset_data,
    asset,
    warnings
):
    result = {}

    # ------------------------------------------------------------------------
    # Blueprint descriptive fields
    # ------------------------------------------------------------------------

    for output_name, property_name in (
        ("display_name", "blueprint_display_name"),
        ("description", "blueprint_description"),
        ("category", "blueprint_category"),
    ):

        success, value = _safe_editor_property(
            asset,
            property_name
        )

        if success and value:
            result[output_name] = _stringify(value)

    # ------------------------------------------------------------------------
    # Asset Registry class tags
    # ------------------------------------------------------------------------

    result["generated_class"] = _registry_tag(
        asset_data,
        "GeneratedClass"
    )

    result["parent_class"] = (
        _registry_tag(
            asset_data,
            "ParentClass"
        )
        or
        _registry_tag(
            asset_data,
            "NativeParentClass"
        )
    )

    # GeneratedClass through editor API is useful even when the registry tag
    # is missing.
    try:
        generated_class = unreal.BlueprintEditorLibrary.generated_class(
            asset
        )

        if generated_class is not None:

            result["generated_class_object"] = (
                generated_class.get_path_name()
            )

    except Exception as error:

        warnings.append(
            "Unable to resolve generated Blueprint class: {}".format(
                error
            )
        )

    result["interfaces"] = _extract_interfaces(
        asset
    )

    result["components"] = _extract_components(
        asset,
        warnings
    )

    result["variables"] = _extract_variables(
        asset,
        warnings
    )

    result["graphs"] = _extract_graph_summary(
        asset
    )

    result["extraction_status"] = {
        "parent_class": "complete",
        "generated_class": "complete",
        "interfaces": "best_effort",
        "components": (
            "complete"
            if _is_actor_blueprint(asset)
            else "not_applicable"
    ),

        # UE 5.6 Python API boundary.
        # Commit 3 text serialization will populate these exhaustively.
        "member_variables": "deferred_to_commit_3",
        "graph_inventory": "deferred_to_commit_3",
        "graph_nodes": "deferred_to_commit_3",
    }

    return result

# ============================================================================
# Generic asset export
# ============================================================================


def _base_asset_document(
    candidate,
    asset_data,
    architecture_refs
):
    return {
        "schema_version": 1,

        "identity": {
            "name": candidate["asset_name"],
            "package_name": candidate["package_name"],
            "package_path": candidate["package_path"],
            "object_path": candidate["object_path"],
            "relative_package": candidate["relative_package"],
        },

        "classification": {
            "category": candidate["category"],
            "asset_class": candidate["asset_class"],
            "reason": candidate["classification_reason"],
        },

        "architecture": architecture_refs,

        "registry": {
            # Useful generic tags. Not all assets expose every tag.
            "parent_class": (
                _registry_tag(asset_data, "ParentClass")
                or
                _registry_tag(asset_data, "NativeParentClass")
            ),

            "generated_class": _registry_tag(
                asset_data,
                "GeneratedClass"
            ),

            "row_structure": _registry_tag(
                asset_data,
                "RowStructure"
            ),
        },
    }


def _export_one_asset(
    candidate,
    registry,
    candidate_packages,
    dependency_options
):
    warnings = []

    package_name = candidate["package_name"]

    asset_data = _find_asset_data(
        registry,
        package_name,
        candidate["asset_name"]
    )

    if asset_data is None:
        raise RuntimeError(
            "AssetData not found for {}".format(
                package_name
            )
        )

    architecture_refs = _get_architecture_references(
        registry,
        package_name,
        candidate_packages,
        dependency_options
    )

    document = _base_asset_document(
        candidate,
        asset_data,
        architecture_refs
    )

    # ------------------------------------------------------------------------
    # FULL_GRAPH assets
    # ------------------------------------------------------------------------

    if candidate["category"] == "FULL_GRAPH":

        try:
            asset = unreal.AssetRegistryHelpers.get_asset(
                asset_data
            )

            if asset is None:
                raise RuntimeError(
                    "Asset could not be loaded."
                )

            document["blueprint"] = _extract_blueprint_metadata(
                asset_data,
                asset,
                warnings
            )

        except Exception as error:

            document["blueprint"] = None

            warnings.append(
                "Blueprint metadata extraction failed: {}".format(
                    error
                )
            )

    # Structural assets intentionally remain lightweight in Commit 2.
    # Commit 4 will give DataAssets, structs, enums, Behavior Trees,
    # Blackboards and Input assets specialized serializers.

    if warnings:
        document["extraction_warnings"] = warnings

    output_directory = io_utils.asset_output_directory(
        candidate["relative_package"]
    )

    output_path = os.path.join(
        output_directory,
        "asset.json"
    )

    io_utils.write_json(
        output_path,
        document
    )

    return {
        "package_name": package_name,
        "output_path": output_path,
        "warnings": warnings,
        "dependencies": architecture_refs["dependencies"],
    }


# ============================================================================
# Public export
# ============================================================================


def export_metadata(discovery_result):
    """
    Export all Commit-2 architecture metadata.

    Returns a summary used by export_manifest.json.
    """

    registry = unreal.AssetRegistryHelpers.get_asset_registry()

    dependency_options = _make_dependency_options()

    full_graph = discovery_result[
        "assets"
    ]["full_graph"]

    structural = discovery_result[
        "assets"
    ]["structural"]

    candidates = (
        list(full_graph)
        +
        list(structural)
    )

    candidates.sort(
        key=lambda item: item["package_name"].lower()
    )

    candidate_packages = {
        candidate["package_name"]
        for candidate in candidates
    }

    io_utils.recreate_mirror_root()

    unreal.log(
        "[CodeXAI] Exporting architecture metadata for {} assets...".format(
            len(candidates)
        )
    )

    exported = []
    errors = []
    warning_assets = []

    dependency_edges = []

    for index, candidate in enumerate(
        candidates,
        start=1
    ):

        package_name = candidate["package_name"]

        try:

            result = _export_one_asset(
                candidate,
                registry,
                candidate_packages,
                dependency_options
            )

            exported.append(
                package_name
            )

            if result["warnings"]:
                warning_assets.append({
                    "package_name": package_name,
                    "warnings": result["warnings"],
                })

            for dependency in result["dependencies"]:

                dependency_edges.append({
                    "from": package_name,
                    "to": dependency,
                })

        except Exception as error:

            errors.append({
                "package_name": package_name,
                "error": str(error),
            })

            unreal.log_warning(
                "[CodeXAI] Metadata export failed for {}: {}".format(
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
                "[CodeXAI] Metadata progress: {}/{}".format(
                    index,
                    len(candidates)
                )
            )

    dependency_edges.sort(
        key=lambda edge: (
            edge["from"].lower(),
            edge["to"].lower()
        )
    )

    dependency_graph = {
        "schema_version": 1,

        "node_count": len(candidates),
        "edge_count": len(dependency_edges),

        "edges": dependency_edges,
    }

    dependency_graph_path = os.path.join(
        io_utils.get_output_root(),
        "dependency_graph.json"
    )

    io_utils.write_json(
        dependency_graph_path,
        dependency_graph
    )

    return {
        "candidate_count": len(candidates),

        "full_graph_count": len(full_graph),
        "structural_count": len(structural),

        "exported_count": len(exported),
        "error_count": len(errors),
        "warning_asset_count": len(warning_assets),

        "errors": errors,
        "warning_assets": warning_assets,

        "dependency_graph": {
            "path": dependency_graph_path,
            "edge_count": len(dependency_edges),
        },
    }