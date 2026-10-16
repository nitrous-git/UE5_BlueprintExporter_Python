import json
import re

import unreal


# ============================================================================
# Generic values / references
# ============================================================================


def _class_name(value):
    try:
        return value.get_class().get_name()
    except Exception:
        return type(value).__name__


def object_reference(value):
    if value is None:
        return None

    try:
        return {
            "name": value.get_name(),
            "class": value.get_class().get_name(),
            "path": value.get_path_name(),
        }
    except Exception:
        return {
            "name": str(value),
            "class": type(value).__name__,
            "path": None,
        }


def _safe_get(value, property_name, default=None):
    try:
        return value.get_editor_property(
            property_name
        )
    except Exception:
        return default


def _enum_or_scalar(value):
    if value is None:
        return None

    if isinstance(
        value,
        (bool, int, float, str)
    ):
        return value

    if isinstance(
        value,
        unreal.Name
    ):
        return str(value)

    if isinstance(
        value,
        unreal.Text
    ):
        return str(value)

    return str(value)


def serialize_value(value):
    """
    Conservative JSON-safe serializer.

    UObjects become references rather than recursively walking arbitrary object
    graphs. Structs use Unreal's own export_text representation unless a
    serializer below handles them explicitly.
    """

    if value is None:
        return None

    if isinstance(
        value,
        (bool, int, float, str)
    ):
        return value

    if isinstance(
        value,
        (unreal.Name, unreal.Text)
    ):
        return str(value)

    if isinstance(
        value,
        unreal.Object
    ):
        return object_reference(
            value
        )

    if isinstance(
        value,
        unreal.StructBase
    ):
        try:
            return {
                "struct": type(value).__name__,
                "text": value.export_text(),
            }
        except Exception:
            return str(value)

    if isinstance(
        value,
        dict
    ) or hasattr(
        value,
        "items"
    ):
        try:
            return {
                str(key): serialize_value(item)
                for key, item in value.items()
            }
        except Exception:
            pass

    if isinstance(
        value,
        (list, tuple, set)
    ):
        return [
            serialize_value(item)
            for item in value
        ]

    # unreal.Array / unreal.Set / unreal.Map are iterable wrappers.
    try:
        if not isinstance(
            value,
            (str, bytes)
        ):
            return [
                serialize_value(item)
                for item in value
            ]
    except Exception:
        pass

    return str(value)


# ============================================================================
# Raw structural T3D helpers
# ============================================================================


def _split_top_level(
    text,
    delimiter=","
):
    """
    Split a serialized Unreal tuple/list without breaking nested tuples or
    quoted strings.
    """

    parts = []

    start = 0
    depth = 0

    quote = None
    escaped = False

    for index, char in enumerate(
        text
    ):

        if quote is not None:

            if escaped:
                escaped = False

            elif char == "\\":
                escaped = True

            elif char == quote:
                quote = None

            continue

        if char in ('"', "'"):
            quote = char
            continue

        if char in "([{":
            depth += 1
            continue

        if char in ")]}":
            depth -= 1
            continue

        if (
            char == delimiter
            and depth == 0
        ):

            parts.append(
                text[start:index].strip()
            )

            start = index + 1

    tail = text[start:].strip()

    if tail:
        parts.append(
            tail
        )

    return parts


def _decode_t3d_scalar(value):
    if value is None:
        return None

    if not isinstance(
        value,
        str
    ):
        return value

    value = value.strip()

    if value == "None":
        return None

    if value == "True":
        return True

    if value == "False":
        return False

    if (
        len(value) >= 2
        and value[0] == '"'
        and value[-1] == '"'
    ):

        try:
            return json.loads(
                value
            )
        except Exception:
            return (
                value[1:-1]
                .replace('\\"', '"')
                .replace("\\n", "\n")
                .replace("\\\\", "\\")
            )

    if re.fullmatch(
        r"-?\d+",
        value
    ):
        try:
            return int(value)
        except Exception:
            pass

    if re.fullmatch(
        r"-?(?:\d+\.\d*|\d*\.\d+)(?:[Ee][+-]?\d+)?",
        value
    ):
        try:
            return float(value)
        except Exception:
            pass

    return value


def _parse_t3d_tuple(value):
    """
    Parse a flat Unreal key/value tuple while preserving nested values.

    Example:
        (VarName="Foo",VarGuid=...,DefaultValue="(X=1,Y=2)")
    """

    if not isinstance(
        value,
        str
    ):
        return {}

    value = value.strip()

    if (
        value.startswith("(")
        and value.endswith(")")
    ):
        value = value[1:-1]

    result = {}

    for part in _split_top_level(
        value
    ):

        if "=" not in part:
            continue

        key, raw_value = part.split(
            "=",
            1
        )

        result[
            key.strip()
        ] = _decode_t3d_scalar(
            raw_value.strip()
        )

    return result


def _walk_raw_objects(objects):
    for obj in objects or []:

        yield obj

        for child in _walk_raw_objects(
            obj.get(
                "children",
                []
            )
        ):
            yield child


def _raw_property_map(obj):
    if not obj:
        return {}

    return {
        property_record.get(
            "name"
        ): property_record.get(
            "value"
        )
        for property_record in obj.get(
            "properties",
            []
        )
        if property_record.get(
            "name"
        )
    }


def _find_raw_object(
    raw_object_tree,
    object_name
):
    """
    T3D may contain both a declaration block and a detailed block for the same
    subobject. Prefer the occurrence with the most serialized properties.
    """

    matches = [
        obj
        for obj in _walk_raw_objects(
            raw_object_tree
        )
        if obj.get(
            "name"
        ) == object_name
    ]

    if not matches:
        return None

    return max(
        matches,
        key=lambda obj: len(
            obj.get(
                "properties",
                []
            )
        )
    )


def _extract_localized_text(value):
    """
    Extract the human-readable text from Unreal LOCTEXT/NSLOCTEXT source.
    """

    if not isinstance(
        value,
        str
    ):
        return value

    quoted = re.findall(
        r'"((?:\\.|[^"\\])*)"',
        value
    )

    if not quoted:
        return value

    encoded = quoted[-1]

    try:
        return json.loads(
            '"{}"'.format(
                encoded
            )
        )
    except Exception:
        return (
            encoded
            .replace('\\"', '"')
            .replace("\\n", "\n")
            .replace("\\\\", "\\")
        )


def _indexed_property_number(
    property_name,
    prefix
):
    match = re.match(
        r"{}\((\d+)\)$".format(
            re.escape(
                prefix
            )
        ),
        property_name
    )

    if not match:
        return None

    return int(
        match.group(1)
    )


def _serialize_user_struct_fields(
    raw_object_tree
):
    records = []

    for obj in _walk_raw_objects(
        raw_object_tree
    ):

        for property_record in obj.get(
            "properties",
            []
        ):

            property_name = (
                property_record.get(
                    "name"
                )
                or ""
            )

            index = _indexed_property_number(
                property_name,
                "VariablesDescriptions"
            )

            if index is None:
                continue

            definition = _parse_t3d_tuple(
                property_record.get(
                    "value"
                )
            )

            if not definition:
                continue

            records.append(
                (
                    index,
                    definition
                )
            )

    # Declaration/detailed object duplication can theoretically expose the
    # same field more than once. Keep one record per stable field identity.
    fields_by_identity = {}

    for index, definition in records:

        identity = (
            definition.get(
                "VarGuid"
            )
            or definition.get(
                "VarName"
            )
            or str(index)
        )

        fields_by_identity[
            identity
        ] = (
            index,
            definition
        )

    ordered = sorted(
        fields_by_identity.values(),
        key=lambda item: item[0]
    )

    fields = []

    for _, definition in ordered:

        field_type = {
            "category": definition.get(
                "Category"
            ),

            "sub_category": definition.get(
                "SubCategory"
            ),

            "sub_category_object": definition.get(
                "SubCategoryObject"
            ),
        }

        # Remove purely absent type details while keeping category explicit.
        field_type = {
            key: value
            for key, value in field_type.items()
            if (
                key == "category"
                or value is not None
            )
        }

        fields.append({
            "name": (
                definition.get(
                    "FriendlyName"
                )
                or definition.get(
                    "VarName"
                )
            ),

            "internal_name": definition.get(
                "VarName"
            ),

            "guid": definition.get(
                "VarGuid"
            ),

            "type": field_type,

            # Struct defaults are serialized by Unreal as text because they
            # can themselves contain nested Unreal struct syntax.
            "default_value": definition.get(
                "DefaultValue"
            ),

            "current_default_value": definition.get(
                "CurrentDefaultValue"
            ),

            "tooltip": definition.get(
                "ToolTip"
            ),
        })

    return fields


def _serialize_user_enum_values(
    raw_object_tree
):
    root = next(
        iter(
            raw_object_tree or []
        ),
        None
    )

    properties = _raw_property_map(
        root
    )

    display_name_map = properties.get(
        "DisplayNameMap"
    )

    if not isinstance(
        display_name_map,
        str
    ):
        return []

    source = display_name_map.strip()

    if (
        source.startswith("(")
        and source.endswith(")")
    ):
        source = source[1:-1]

    result = []

    for item in _split_top_level(
        source
    ):

        item = item.strip()

        if (
            item.startswith("(")
            and item.endswith(")")
        ):
            item = item[1:-1]

        parts = _split_top_level(
            item
        )

        if len(parts) < 2:
            continue

        result.append({
            "internal_name": _decode_t3d_scalar(
                parts[0]
            ),

            "display_name": _extract_localized_text(
                parts[1]
            ),
        })

    return result


# ============================================================================
# Data Tables
# ============================================================================


def serialize_data_table(asset):
    library = unreal.DataTableFunctionLibrary

    row_struct = (
        library.get_data_table_row_struct(
            asset
        )
    )

    row_names = [
        str(name)
        for name in library.get_data_table_row_names(
            asset
        )
    ]

    column_names = [
        str(name)
        for name in library.get_data_table_column_names(
            asset
        )
    ]

    export_column_names = [
        str(name)
        for name in library.get_data_table_column_export_names(
            asset
        )
    ]

    raw_json = (
        library.export_data_table_to_json_string(
            asset
        )
    )

    rows = []

    if raw_json:
        try:
            rows = json.loads(
                raw_json
            )
        except Exception:
            rows = []

    return {
        "serializer": "data_table",

        "data": {
            "row_struct": object_reference(
                row_struct
            ),

            "row_count": len(
                row_names
            ),

            "row_names": row_names,

            "column_names": column_names,

            "export_column_names": (
                export_column_names
            ),

            # Canonical DataTable contents exported by Unreal itself.
            "rows": rows,
        },
    }


# ============================================================================
# Enhanced Input
# ============================================================================


def _object_ref_list(values):
    if values is None:
        return []

    return [
        object_reference(value)
        for value in values
        if value is not None
    ]


def serialize_input_action(asset):
    return {
        "serializer": "input_action",

        "data": {
            "value_type": _enum_or_scalar(
                _safe_get(
                    asset,
                    "value_type"
                )
            ),

            "accumulation_behavior": _enum_or_scalar(
                _safe_get(
                    asset,
                    "accumulation_behavior"
                )
            ),

            "action_description": _enum_or_scalar(
                _safe_get(
                    asset,
                    "action_description"
                )
            ),

            "consume_input": _safe_get(
                asset,
                "consume_input"
            ),

            "consumes_action_and_axis_mappings": _safe_get(
                asset,
                "consumes_action_and_axis_mappings"
            ),

            "reserve_all_mappings": _safe_get(
                asset,
                "reserve_all_mappings"
            ),

            "trigger_when_paused": _safe_get(
                asset,
                "trigger_when_paused"
            ),

            "trigger_events_that_consume_legacy_keys": _safe_get(
                asset,
                "trigger_events_that_consume_legacy_keys"
            ),

            "triggers": _object_ref_list(
                _safe_get(
                    asset,
                    "triggers",
                    []
                )
            ),

            "modifiers": _object_ref_list(
                _safe_get(
                    asset,
                    "modifiers",
                    []
                )
            ),

            "player_mappable_key_settings": serialize_value(
                _safe_get(
                    asset,
                    "player_mappable_key_settings"
                )
            ),
        },
    }


def _key_name(key):
    if key is None:
        return None

    try:
        return str(
            key.get_editor_property(
                "key_name"
            )
        )
    except Exception:
        pass

    try:
        return key.export_text()
    except Exception:
        return str(key)


def _serialize_enhanced_mapping(mapping):
    action = _safe_get(
        mapping,
        "action"
    )

    key = _safe_get(
        mapping,
        "key"
    )

    return {
        "action": object_reference(
            action
        ),

        "key": _key_name(
            key
        ),

        "triggers": _object_ref_list(
            _safe_get(
                mapping,
                "triggers",
                []
            )
        ),

        "modifiers": _object_ref_list(
            _safe_get(
                mapping,
                "modifiers",
                []
            )
        ),

        "setting_behavior": _enum_or_scalar(
            _safe_get(
                mapping,
                "setting_behavior"
            )
        ),

        "player_mappable_key_settings": serialize_value(
            _safe_get(
                mapping,
                "player_mappable_key_settings"
            )
        ),
    }


def serialize_input_mapping_context(asset):
    mappings = _safe_get(
        asset,
        "mappings",
        []
    )

    return {
        "serializer": "input_mapping_context",

        "data": {
            "context_description": _enum_or_scalar(
                _safe_get(
                    asset,
                    "context_description"
                )
            ),

            "registration_tracking_mode": _enum_or_scalar(
                _safe_get(
                    asset,
                    "registration_tracking_mode"
                )
            ),

            "input_mode_filter_options": serialize_value(
                _safe_get(
                    asset,
                    "input_mode_filter_options"
                )
            ),

            "input_mode_query_override": serialize_value(
                _safe_get(
                    asset,
                    "input_mode_query_override"
                )
            ),

            "mapping_count": len(
                mappings
            ),

            "mappings": [
                _serialize_enhanced_mapping(
                    mapping
                )
                for mapping in mappings
            ],
        },
    }


# ============================================================================
# Blackboard / Behavior Tree
# ============================================================================


def _key_type_details(
    key_type,
    raw_object_tree=None
):
    if key_type is None:
        return None

    result = object_reference(
        key_type
    )

    # Prefer direct UE Python properties when available.
    direct_properties = {
        "base_class": "base_class",
        "enum_type": "enum_type",
        "enum_name": "enum_name",
    }

    for property_name, output_name in direct_properties.items():

        value = _safe_get(
            key_type,
            property_name
        )

        if value is not None:

            result[
                output_name
            ] = serialize_value(
                value
            )

    # UE 5.6 does not consistently expose every concrete key-type property
    # through Python. Fall back to the already-exported T3D subobject.
    raw_object = _find_raw_object(
        raw_object_tree,
        key_type.get_name()
    )

    raw_properties = _raw_property_map(
        raw_object
    )

    raw_mapping = {
        "BaseClass": "base_class",
        "EnumType": "enum_type",
        "EnumName": "enum_name",
        "bIsEnumNameValid": "enum_name_valid",
    }

    for raw_name, output_name in raw_mapping.items():

        if (
            output_name not in result
            and raw_name in raw_properties
        ):

            result[
                output_name
            ] = raw_properties[
                raw_name
            ]

    return result


def _serialize_blackboard_entry(
    entry,
    raw_object_tree=None
):
    key_type = _safe_get(
        entry,
        "key_type"
    )

    return {
        "name": str(
            _safe_get(
                entry,
                "entry_name",
                ""
            )
        ),

        "category": str(
            _safe_get(
                entry,
                "entry_category",
                ""
            )
        ),

        "description": _safe_get(
            entry,
            "entry_description",
            ""
        ),

        "instance_synced": bool(
            _safe_get(
                entry,
                "instance_synced",
                False
            )
        ),

        "key_type": _key_type_details(
            key_type,
            raw_object_tree
        ),
    }


def serialize_blackboard(
    asset,
    raw_object_tree=None
):
    keys = _safe_get(
        asset,
        "keys",
        []
    )

    parent_keys = _safe_get(
        asset,
        "parent_keys",
        []
    )

    parent = _safe_get(
        asset,
        "parent"
    )

    return {
        "serializer": "blackboard",

        "data": {
            "parent": object_reference(
                parent
            ),

            "key_count": len(
                keys
            ),

            "keys": [
                _serialize_blackboard_entry(
                    entry,
                    raw_object_tree
                )
                for entry in keys
            ],

            "inherited_key_count": len(
                parent_keys
            ),

            "inherited_keys": [
                _serialize_blackboard_entry(
                    entry,
                    raw_object_tree
                )
                for entry in parent_keys
            ],
        },
    }


def serialize_behavior_tree(asset):
    blackboard = None

    try:
        blackboard = asset.get_blackboard_asset()
    except Exception:
        pass

    return {
        "serializer": "behavior_tree",

        "data": {
            "blackboard": object_reference(
                blackboard
            ),

            # UE 5.6 exposes the referenced Blackboard directly, but not a
            # complete stable Python traversal API for every BT editor node.
            # The normalized raw_object_tree in structural.json remains the
            # source for BT node/decorator/service details.
            "tree_source": "raw_object_tree",
        },
    }


# ============================================================================
# User-defined Enum / Struct / StateTree / generic DataAssets
# ============================================================================


def serialize_user_defined_enum(
    asset,
    raw_object_tree=None
):
    values = _serialize_user_enum_values(
        raw_object_tree
    )

    return {
        "serializer": "user_defined_enum",

        "data": {
            "enum_description": _enum_or_scalar(
                _safe_get(
                    asset,
                    "enum_description"
                )
            ),

            # get_enum_path_name() stringifies TopLevelAssetPath rather
            # verbosely in UE 5.6. get_path_name() is the canonical asset
            # object path we actually want in AI context.
            "enum_path": asset.get_path_name(),

            "value_count": len(
                values
            ),

            "values": values,

            "definition_source": "raw_object_tree",
        },
    }


def serialize_user_defined_struct(
    asset,
    raw_object_tree=None
):
    fields = _serialize_user_struct_fields(
        raw_object_tree
    )

    return {
        "serializer": "user_defined_struct",

        "data": {
            "struct_path": asset.get_path_name(),

            "field_count": len(
                fields
            ),

            "fields": fields,

            "definition_source": "raw_object_tree",
        },
    }


def serialize_state_tree(asset):
    return {
        "serializer": "state_tree",

        "data": {
            "definition_source": "raw_object_tree",
        },
    }


def serialize_data_asset(asset):
    return {
        "serializer": "data_asset",

        "data": {
            "asset_class": _class_name(
                asset
            ),

            # Arbitrary project-specific DataAsset subclasses do not have a
            # generic Python property-enumeration API. Their complete exported
            # property tree is retained below in raw_object_tree.
            "definition_source": "raw_object_tree",
        },
    }


def serialize_generic(asset):
    return {
        "serializer": "generic_structural",

        "data": {
            "asset_class": _class_name(
                asset
            ),

            "definition_source": "raw_object_tree",
        },
    }


# ============================================================================
# Dispatcher
# ============================================================================


def serialize(
    asset,
    raw_object_tree=None
):
    class_name = asset.get_class().get_name()

    if isinstance(
        asset,
        unreal.DataTable
    ):
        return serialize_data_table(
            asset
        )

    if class_name == "InputAction":
        return serialize_input_action(
            asset
        )

    if class_name == "InputMappingContext":
        return serialize_input_mapping_context(
            asset
        )

    if class_name == "BlackboardData":
        return serialize_blackboard(
            asset,
            raw_object_tree
        )

    if class_name == "BehaviorTree":
        return serialize_behavior_tree(
            asset
        )

    if class_name == "UserDefinedEnum":
        return serialize_user_defined_enum(
            asset,
            raw_object_tree
        )

    if class_name == "UserDefinedStruct":
        return serialize_user_defined_struct(
            asset,
            raw_object_tree
        )

    if class_name == "StateTree":
        return serialize_state_tree(
            asset
        )

    if isinstance(
        asset,
        unreal.DataAsset
    ):
        return serialize_data_asset(
            asset
        )

    return serialize_generic(
        asset
    )
