"""UMG Widget Blueprint designer/source exporter for UE5 Blueprint Exporter.

Install at: <Project>/Content/Python/UE5_BP_Exporter/widget_exporter.py

Designed for UE 5.6+ Unreal Editor's Python environment. No runtime widgets are
created, no Widget Blueprints are modified, and no source assets are saved.

Standalone:
    from UE5_BP_Exporter import widget_exporter
    widget_exporter.export_single('/Game/UI/WBP_Example')

Batch, after existing metadata / graph passes:
    widget_summary = widget_exporter.export_widget_source(discovery_result)

Output, per WidgetBlueprint:
    <export mirror>/<relative asset package>/widget_tree.json

Caveat: access to UWidgetBlueprint.WidgetTree / UWidgetTree.RootWidget is not
uniformly exposed to Python in all UE versions. Missing API surfaces yield
explicit 'unavailable' sections rather than a fabricated empty widget tree.
"""

import json
import os

import unreal

# UE5_BP_Exporter/__init__.py in v0.5.0 aliases legacy 'CodeXAI'.
from UE5_BP_Exporter import config, io_utils

SCHEMA_VERSION = 1
MAX_DEPTH = 64
MAX_ITEMS = 256
MAX_TEXT = 4096

# Properties read from actual editor widget templates; not runtime geometry.
WIDGET_PROPERTIES = (
    "visibility", "is_enabled", "is_variable", "render_opacity",
    "render_transform", "render_transform_pivot", "clipping",
    "tool_tip_text", "cursor", "navigation", "flow_direction_preference",
    "text", "hint_text", "color_and_opacity", "shadow_color_and_opacity",
    "font", "justification", "auto_wrap_text", "wrap_text_at",
    "minimum_desired_width", "margin", "line_height_percentage",
    "brush", "background", "background_color", "widget_style", "style",
    "percent", "fill_color_and_opacity", "bar_fill_type", "bar_fill_style",
    "is_marquee", "orientation", "padding", "horizontal_alignment",
    "vertical_alignment", "min_desired_width", "min_desired_height",
    "max_desired_width", "max_desired_height", "width_override",
    "height_override", "size_to_content", "spacing", "slot_padding",
    "active_widget_index", "content_color_and_opacity",
)

SLOT_PROPERTIES = (
    "layout_data", "anchors", "offsets", "alignment", "position", "size",
    "z_order", "auto_size", "padding", "horizontal_alignment",
    "vertical_alignment", "min_size", "max_size", "fill_size",
)

# A few known nested struct fields make the JSON useful, rather than merely
# storing opaque export_text strings. Other structs retain export_text().
STRUCT_PROPERTIES = {
    "Vector2D": ("x", "y"),
    "Vector": ("x", "y", "z"),
    "LinearColor": ("r", "g", "b", "a"),
    "Color": ("r", "g", "b", "a"),
    "Margin": ("left", "top", "right", "bottom"),
    "Anchors": ("minimum", "maximum"),
    "AnchorData": ("offsets", "anchors", "alignment"),
    "WidgetTransform": ("translation", "scale", "shear", "angle"),
    "SlateBrush": ("resource_object", "image_size", "tint_color", "draw_as", "tiling", "margin"),
    "SlateColor": ("specified_color", "color_use_rule"),
}


def _name(obj):
    if obj is None:
        return None
    try:
        return str(obj.get_name())
    except Exception:
        return str(obj)


def _class(obj):
    try:
        return str(obj.get_class().get_name())
    except Exception:
        return type(obj).__name__


def _reference(obj):
    if obj is None:
        return None
    result = {"name": _name(obj), "class": _class(obj)}
    try:
        result["path"] = str(obj.get_path_name())
    except Exception:
        result["path"] = None
    return result


def _property(obj, property_name):
    """Best effort across native properties, Python-proxied attributes."""
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


def _read_first(obj, names):
    for name in names:
        found, value = _property(obj, name)
        if found and value is not None:
            return value
    return None


def _call(obj, method, *args):
    try:
        f = getattr(obj, method)
        return True, f(*args)
    except Exception:
        return False, None


def _is_unreal_object(obj):
    try:
        return isinstance(obj, unreal.Object)
    except Exception:
        return False


def _is_unreal_struct(obj):
    try:
        return isinstance(obj, unreal.StructBase)
    except Exception:
        return False


def _value(value, depth=0):
    """Bounded, JSON-safe read-only conversion; never traverses UObject refs."""
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, str):
        return value[:MAX_TEXT]
    if _is_unreal_object(value):
        return _reference(value)
    if depth > 5:
        return str(value)[:MAX_TEXT]
    if _is_unreal_struct(value):
        type_name = type(value).__name__
        fields = STRUCT_PROPERTIES.get(type_name, ())
        result = {"struct": type_name}
        for field in fields:
            found, item = _property(value, field)
            if found:
                result[field] = _value(item, depth + 1)
        # Store authoritative Unreal format as fallback for engine-specific
        # struct fields (e.g. FSlateFontInfo, FButtonStyle, custom styles).
        ok, raw = _call(value, "export_text")
        if ok:
            result["text"] = str(raw)[:MAX_TEXT]
        return result
    # Unreal's Name/Text / enums serialize as stable strings.
    if isinstance(value, dict):
        return {
            str(key): _value(val, depth + 1)
            for key, val in list(value.items())[:MAX_ITEMS]
        }
    if isinstance(value, (tuple, list, set)):
        return [_value(v, depth + 1) for v in list(value)[:MAX_ITEMS]]
    if not isinstance(value, (bytes, bytearray, str)):
        try:
            iterator = iter(value)
        except Exception:
            pass
        else:
            values = []
            for i, item in enumerate(iterator):
                if i >= MAX_ITEMS:
                    break
                values.append(_value(item, depth + 1))
            return values
    return str(value)[:MAX_TEXT]


def _properties(obj, names):
    props = {}
    for name in dict.fromkeys(names):
        found, value = _property(obj, name)
        if found and value is not None:
            props[name] = _value(value)
    return props


def _find_template_tree(blueprint):
    """Find an existing tree. Never spawn a UserWidget or compile the BP."""
    candidates = [("blueprint", blueprint)]
    generated = None
    try:
        generated = unreal.BlueprintEditorLibrary.generated_class(blueprint)
    except Exception:
        generated = _read_first(blueprint, ("generated_class",))
    if generated is not None:
        candidates.append(("generated_class", generated))
        try:
            default_object = unreal.get_default_object(generated)
        except Exception:
            default_object = None
        if default_object is not None:
            candidates.append(("class_default_object", default_object))
    for origin, obj in candidates:
        tree = _read_first(obj, ("widget_tree",))
        if tree is not None:
            return tree, origin

        # UE5 often keeps WidgetTree as a named subobject, but hides the
        # WidgetTree UPROPERTY from its Python WidgetBlueprint wrapper.
        # find_object(outer, name) is a documented read-only UE5 Python API.
        # Do not use new_object(), create_widget(), or any editor mutation.
        try:
            tree = unreal.find_object(obj, "WidgetTree")
        except Exception:
            tree = None
        if tree is not None and _class(tree) == "WidgetTree":
            return tree, origin + ".WidgetTree subobject"
    return None, None


def _root_widget(tree, warnings=None):
    if tree is None:
        return None
    root = _read_first(tree, ("root_widget",))
    if root is not None:
        return root
    for method in ("get_root_widget", "get_root"):
        ok, root = _call(tree, method)
        if ok and root is not None:
            return root

    # UE5 can hide UWidgetTree.RootWidget from Python, even if WidgetTree is
    # available by find_object(). As a last resort, search already-loaded
    # Widget UObjects whose immediate outer is this tree. This is READ ONLY.
    # Use a type-scoped iterator, and only infer a root if unambiguous.
    candidates = []
    try:
        iterator = unreal.ObjectIterator(unreal.Widget)
        tree_path = _identity_key(tree)
        for widget in iterator:
            ok, outer = _call(widget, "get_outer")
            if ok and outer is not None and _identity_key(outer) == tree_path:
                candidates.append(widget)
                if len(candidates) >= MAX_ITEMS:
                    break
    except Exception:
        return None
    roots = []
    for widget in candidates:
        ok, parent = _call(widget, "get_parent")
        if ok and parent is None:
            roots.append(widget)
    if len(roots) == 1:
        if warnings is not None:
            warnings.append(
                "RootWidget was inferred from loaded template widgets "
                "(ObjectIterator); verify this designer hierarchy in the editor."
            )
        return roots[0]
    return None


def _children(widget):
    """PanelWidget and ContentWidget support with no editor-side changes."""
    ok, count = _call(widget, "get_children_count")
    if ok and count is not None:
        try:
            count = max(0, min(int(count), MAX_ITEMS))
            return [child for i in range(count)
                    for success, child in (_call(widget, "get_child_at", i),)
                    if success and child is not None]
        except Exception:
            pass
    ok, content = _call(widget, "get_content")
    if ok and content is not None:
        return [content]
    return []


def _identity_key(widget):
    try:
        return str(widget.get_path_name())
    except Exception:
        return str(id(widget))


def _read_widget(widget, visited, warnings, depth=0):
    if depth > MAX_DEPTH:
        warnings.append("Widget tree depth limit reached at {}".format(_name(widget)))
        return {"reference": _reference(widget), "truncated": "depth"}
    key = _identity_key(widget)
    if key in visited:
        return {"reference": _reference(widget), "duplicate": True}
    visited.add(key)

    slot = _read_first(widget, ("slot",))
    record = {
        "name": _name(widget),
        "class": _class(widget),
        "path": key,
        "properties": _properties(widget, WIDGET_PROPERTIES),
        "slot": None,
        "children": [],
    }
    if slot is not None:
        record["slot"] = {
            "class": _class(slot),
            "properties": _properties(slot, SLOT_PROPERTIES),
        }
        # A CanvasPanelSlot can expose richer getters even if its editor
        # fields don't show up in Python.
        for method, key_name in (
            ("get_position", "position"),
            ("get_size", "size"),
            ("get_anchors", "anchors"),
            ("get_offsets", "offsets"),
            ("get_alignment", "alignment"),
            ("get_z_order", "z_order"),
            ("get_auto_size", "auto_size"),
        ):
            ok, value = _call(slot, method)
            if ok and value is not None:
                record["slot"]["properties"].setdefault(key_name, _value(value))
    for child in _children(widget):
        record["children"].append(_read_widget(child, visited, warnings, depth + 1))
    return record


def _serialize_binding(binding):
    if _is_unreal_struct(binding):
        return {
            "object_name": _value(_read_first(binding, ("object_name",))),
            "property_name": _value(_read_first(binding, ("property_name",))),
            "function_name": _value(_read_first(binding, ("function_name",))),
            "source_path": _value(_read_first(binding, ("source_path",))),
            "raw": _value(binding),
        }
    return _value(binding)


def _serialize_animation(animation):
    obj = _reference(animation)
    if obj is None:
        return None
    obj["display_label"] = _value(_read_first(animation, ("display_label", "display_name")))
    scene = _read_first(animation, ("movie_scene",))
    if scene is not None:
        obj["movie_scene"] = _reference(scene)
    bindings = _read_first(animation, ("animation_bindings",))
    if bindings is not None:
        obj["bindings"] = [_serialize_binding(x) for x in list(bindings)[:MAX_ITEMS]]
    return obj


def _object_sequence(obj, prop_names):
    for name in prop_names:
        found, array = _property(obj, name)
        if found and array is not None:
            try:
                return list(array)[:MAX_ITEMS], name
            except Exception:
                pass
    return None, None


def _extract(blueprint, package_name):
    warnings = []
    template_tree, source = _find_template_tree(blueprint)
    root = _root_widget(template_tree, warnings)
    visited = set()

    # Blueprint edit-time widget animations and bindings are not guaranteed
    # available via the UE5.6 Python reflection surface.
    animations, anim_source = _object_sequence(blueprint, ("animations",))
    bindings, binding_source = _object_sequence(
        blueprint, ("bindings", "property_bindings")
    )

    if template_tree is None:
        warnings.append(
            "WidgetTree is not exposed by this UE Python API. "
            "Designer hierarchy and layout cannot be extracted from the asset."
        )
    elif root is None:
        warnings.append(
            "WidgetTree was found, but RootWidget is not exposed/assigned. "
            "Designer hierarchy is unavailable."
        )
    if animations is None:
        warnings.append("Widget animations are not exposed through Blueprint editor properties.")
    if bindings is None:
        warnings.append("Designer property bindings are not exposed through Blueprint editor properties.")

    tree = _read_widget(root, visited, warnings) if root is not None else None
    return {
        "schema_version": SCHEMA_VERSION,
        "asset": {"package_name": package_name, "class": _class(blueprint)},
        "designer": {
            "status": "available" if tree is not None else "unavailable",
            "source": source,
            "root": tree,
            "widget_count": len(visited),
        },
        "animations": {
            "status": "available" if animations is not None else "unavailable",
            "source": anim_source,
            "items": [_serialize_animation(a) for a in animations] if animations is not None else [],
        },
        "bindings": {
            "status": "available" if bindings is not None else "unavailable",
            "source": binding_source,
            "items": [_serialize_binding(b) for b in bindings] if bindings is not None else [],
        },
        "warnings": warnings,
    }


def _export_one(candidate):
    package_name = str(candidate["package_name"])
    blueprint = unreal.EditorAssetLibrary.load_asset(package_name)
    if blueprint is None:
        raise RuntimeError("Widget Blueprint could not be loaded: {}".format(package_name))
    actual_class = _class(blueprint)
    if actual_class != "WidgetBlueprint":
        # Class checks avoid accidental writes for non-WidgetBlueprint assets.
        if not isinstance(blueprint, getattr(unreal, "WidgetBlueprint", type(None))):
            raise TypeError("Expected WidgetBlueprint; {} is {}".format(package_name, actual_class))

    document = _extract(blueprint, package_name)
    output_directory = io_utils.asset_output_directory(candidate["relative_package"])
    os.makedirs(output_directory, exist_ok=True)
    output_path = os.path.join(output_directory, "widget_tree.json")
    io_utils.write_json(output_path, document)

    # Follow the graph/structural export conventions: link the new result in
    # generated asset.json if the architecture metadata pass already ran.
    asset_json_path = os.path.join(output_directory, "asset.json")
    if os.path.isfile(asset_json_path):
        try:
            with open(asset_json_path, "r", encoding="utf-8") as stream:
                asset_document = json.load(stream)
            asset_document["widget_designer"] = {
                "file": "widget_tree.json",
                "status": document["designer"]["status"],
                "widget_count": document["designer"]["widget_count"],
            }
            io_utils.write_json(asset_json_path, asset_document)
        except (OSError, ValueError, TypeError) as error:
            document["warnings"].append(
                "Could not update generated asset.json link: {}".format(error)
            )
            io_utils.write_json(output_path, document)
    return {
        "package_name": package_name,
        "file": output_path,
        "widget_count": document["designer"]["widget_count"],
        "designer_status": document["designer"]["status"],
        "animation_count": len(document["animations"]["items"]),
        "binding_count": len(document["bindings"]["items"]),
        "warnings": document["warnings"],
    }


def export_single(package_name):
    """Export one WidgetBlueprint under the configured ROOT_PATH.

    For a clean result, run *after* Full Export has recreated the mirror; it
    does not clear anything itself and does not require a discovery sweep.
    """
    root = str(config.ROOT_PATH).replace("\\", "/").rstrip("/")
    path = str(package_name).replace("\\", "/").rstrip("/")
    if not path.startswith(root + "/"):
        raise ValueError("WidgetBlueprint is outside ROOT_PATH: {}".format(path))
    return _export_one({
        "package_name": path,
        "relative_package": path[len(root) + 1:],
    })


def export_widget_source(discovery_result):
    """Batch export WidgetBlueprint designers from an existing audit result.

    Call after metadata_exporter.export_metadata() since that stage clears the
    mirror. Per-asset errors are recorded and do not abort other exports.
    """
    candidates = [
        item for item in discovery_result["assets"]["full_graph"]
        if item.get("asset_class", {}).get("name") == "WidgetBlueprint"
    ]
    candidates.sort(key=lambda c: c["package_name"].lower())
    results = []
    errors = []
    warnings = []
    widget_count = 0
    partial_count = 0
    for index, candidate in enumerate(candidates, 1):
        try:
            result = _export_one(candidate)
            results.append({"package_name": result["package_name"],
                            "designer_status": result["designer_status"],
                            "widget_count": result["widget_count"]})
            widget_count += result["widget_count"]
            if result["designer_status"] != "available":
                partial_count += 1
            if result["warnings"]:
                warnings.append({"package_name": result["package_name"],
                                 "warnings": result["warnings"]})
        except Exception as error:
            errors.append({"package_name": candidate["package_name"],
                           "error": str(error)})
            unreal.log_warning("[UE5_BP_Exporter] Widget export failed: {}: {}".format(
                candidate["package_name"], error))
        if index == 1 or index % 25 == 0 or index == len(candidates):
            unreal.log("[UE5_BP_Exporter] Widget Designer progress: {}/{}".format(
                index, len(candidates)))
    summary = {
        "candidate_count": len(candidates),
        "exported_count": len(results),
        "widget_count": widget_count,
        "designer_unavailable_count": partial_count,
        "warning_asset_count": len(warnings),
        "error_count": len(errors),
        "errors": errors,
        "warning_assets": warnings,
        "assets": results,
    }
    unreal.log("[UE5_BP_Exporter] Widget Designer export: {}/{} assets, {} widgets, {} unavailable trees".format(
        summary["exported_count"], len(candidates), widget_count, partial_count))
    return summary
