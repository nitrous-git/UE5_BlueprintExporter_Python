import json
import re

from CodeXAI.graphs import text_io

# ============================================================================
# Internal T3D object tree
# ============================================================================


class _ObjectBlock:
    def __init__(
        self,
        name=None,
        class_path=None,
        export_path=None,
        explicit_class=False
    ):
        self.name = name
        self.class_path = class_path
        self.export_path = export_path
        self.explicit_class = explicit_class

        self.properties = []
        self.children = []


def _parse_object_header(line):
    text = line.strip()

    class_match = re.search(
        r"\bClass=([^\s]+)",
        text
    )

    explicit_class = class_match is not None

    class_path = (
        class_match.group(1)
        if class_match
        else None
    )

    name_match = re.search(
        r'\bName="([^"]*)"',
        text
    )

    name = (
        name_match.group(1)
        if name_match
        else None
    )

    export_match = re.search(
        r'\bExportPath="([^"]*)"',
        text
    )

    export_path = (
        export_match.group(1)
        if export_match
        else None
    )

    # Detailed T3D object blocks usually omit Class=, but ExportPath starts
    # with the actual UObject class:
    #
    # /Script/Engine.EdGraph'/Game/...'
    if class_path is None and export_path:

        type_match = re.match(
            r"([^']+)'",
            export_path
        )

        if type_match:
            class_path = type_match.group(1)

    return _ObjectBlock(
        name=name,
        class_path=class_path,
        export_path=export_path,
        explicit_class=explicit_class
    )


def _parse_object_tree(text):
    roots = []
    stack = []

    for source_line in text.splitlines():

        stripped = source_line.strip()

        if stripped.startswith("Begin Object"):

            obj = _parse_object_header(
                source_line
            )

            if stack:
                stack[-1].children.append(
                    obj
                )
            else:
                roots.append(
                    obj
                )

            stack.append(
                obj
            )

        elif stripped == "End Object":

            if not stack:
                raise ValueError(
                    "T3D contains unmatched End Object."
                )

            stack.pop()

        elif stack and stripped:

            stack[-1].properties.append(
                stripped
            )

    if stack:
        raise ValueError(
            "T3D contains unclosed Begin Object blocks."
        )

    return roots


# ============================================================================
# T3D value parsing
# ============================================================================


def _split_top_level(text, delimiter=","):
    """
    Split on delimiter only when it is not nested inside:
        ()
        []
        {}
        quoted strings

    Unreal's pin tuples contain many nested tuples, so str.split(",") is not
    sufficient.
    """

    parts = []

    start = 0
    depth = 0

    quote = None
    escaped = False

    for index, char in enumerate(text):

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


def _decode_scalar(value):
    if value is None:
        return None

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
                .replace("\\\\", "\\")
                .replace("\\n", "\n")
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


def _localized_text(value):
    if value is None:
        return None

    value = value.strip()

    if (
        value.startswith("NSLOCTEXT(")
        or value.startswith("LOCTEXT(")
    ):

        quoted = re.findall(
            r'"((?:\\.|[^"\\])*)"',
            value
        )

        if quoted:
            return (
                quoted[-1]
                .replace('\\"', '"')
                .replace("\\n", "\n")
            )

    return _decode_scalar(
        value
    )


def _parse_tuple(value):
    """
    Parse:
        (Key=A,Other=(Nested=B),Text="Hello, World")

    Values remain encoded strings until the caller chooses how to decode them.
    """

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

        if not part:
            continue

        if "=" not in part:

            result.setdefault(
                "_items",
                []
            ).append(
                part
            )

            continue

        key, raw_value = part.split(
            "=",
            1
        )

        result[
            key.strip()
        ] = raw_value.strip()

    return result


def _property_map(properties):
    result = {}

    for line in properties:

        if line.startswith(
            "CustomProperties Pin "
        ):
            continue

        if "=" not in line:
            continue

        key, value = line.split(
            "=",
            1
        )

        result[
            key.strip()
        ] = value.strip()

    return result


def _parse_reference(value):
    if not value:
        return None

    value = value.strip()

    if not value.startswith("("):
        return _decode_scalar(
            value
        )

    raw = _parse_tuple(
        value
    )

    return {
        key: _decode_scalar(item)
        for key, item in raw.items()
        if key != "_items"
    }


# ============================================================================
# Variables
# ============================================================================


def _parse_variable(line):
    _, value = line.split(
        "=",
        1
    )

    data = _parse_tuple(
        value
    )

    variable_type = _parse_tuple(
        data.get(
            "VarType",
            "()"
        )
    )

    def get_value(
        source,
        key,
        default=None
    ):
        if key not in source:
            return default

        return _decode_scalar(
            source[key]
        )

    return {
        "name": get_value(
            data,
            "VarName"
        ),

        "guid": get_value(
            data,
            "VarGuid"
        ),

        "friendly_name": get_value(
            data,
            "FriendlyName"
        ),

        "category": _localized_text(
            data.get(
                "Category"
            )
        ),

        "property_flags": get_value(
            data,
            "PropertyFlags"
        ),

        # Present only when Unreal serializes a declaration-level default.
        "default_value": get_value(
            data,
            "DefaultValue"
        ),

        "type": {
            "category": get_value(
                variable_type,
                "PinCategory"
            ),

            "sub_category": get_value(
                variable_type,
                "PinSubCategory"
            ),

            "sub_category_object": get_value(
                variable_type,
                "PinSubCategoryObject"
            ),

            "container": get_value(
                variable_type,
                "ContainerType"
            ),

            "is_reference": get_value(
                variable_type,
                "bIsReference",
                False
            ),

            "is_const": get_value(
                variable_type,
                "bIsConst",
                False
            ),

            "is_weak_pointer": get_value(
                variable_type,
                "bIsWeakPointer",
                False
            ),
        },
    }


# ============================================================================
# Pins
# ============================================================================


def _parse_pin(line):
    prefix = "CustomProperties Pin "

    payload = line[
        len(prefix):
    ].strip()

    data = _parse_tuple(
        payload
    )

    def get_value(
        key,
        default=None
    ):
        if key not in data:
            return default

        return _decode_scalar(
            data[key]
        )

    pin = {
        "id": get_value(
            "PinId"
        ),

        "name": get_value(
            "PinName"
        ),

        "friendly_name": _localized_text(
            data.get(
                "PinFriendlyName"
            )
        ),

        "direction": (
            "output"
            if get_value("Direction") == "EGPD_Output"
            else "input"
        ),

        "type": {
            "category": get_value(
                "PinType.PinCategory"
            ),

            "sub_category": get_value(
                "PinType.PinSubCategory"
            ),

            "sub_category_object": get_value(
                "PinType.PinSubCategoryObject"
            ),

            "container": get_value(
                "PinType.ContainerType"
            ),

            "is_reference": get_value(
                "PinType.bIsReference",
                False
            ),

            "is_const": get_value(
                "PinType.bIsConst",
                False
            ),

            "is_weak_pointer": get_value(
                "PinType.bIsWeakPointer",
                False
            ),

            "is_uobject_wrapper": get_value(
                "PinType.bIsUObjectWrapper",
                False
            ),
        },

        "default_value": get_value(
            "DefaultValue"
        ),

        "autogenerated_default_value": get_value(
            "AutogeneratedDefaultValue"
        ),

        "default_object": get_value(
            "DefaultObject"
        ),

        "hidden": get_value(
            "bHidden",
            False
        ),

        "orphaned": get_value(
            "bOrphanedPin",
            False
        ),

        "links": [],
    }

    member_reference = data.get(
        "PinType.PinSubCategoryMemberReference"
    )

    if (
        member_reference
        and member_reference != "()"
    ):

        pin["type"][
            "sub_category_member_reference"
        ] = _parse_reference(
            member_reference
        )

    linked_to = data.get(
        "LinkedTo"
    )

    if linked_to:

        linked_to = linked_to.strip()

        if (
            linked_to.startswith("(")
            and linked_to.endswith(")")
        ):
            linked_to = linked_to[1:-1]

        for item in _split_top_level(
            linked_to
        ):

            item = item.strip()

            if not item:
                continue

            match = re.match(
                r"(.+?)\s+([A-Fa-f0-9]{32})$",
                item
            )

            if match:

                pin["links"].append({
                    "node": match.group(1).strip(),
                    "pin_id": match.group(2),
                })

            else:

                # Keep unsupported link syntax visible instead of silently
                # dropping it.
                pin["links"].append({
                    "raw": item
                })

    return pin


# ============================================================================
# Nodes
# ============================================================================


def _member_name(reference):
    if not reference:
        return None

    data = _parse_tuple(
        reference
    )

    raw = data.get(
        "MemberName"
    )

    return (
        _decode_scalar(raw)
        if raw is not None
        else None
    )


def _node_title(class_path, properties):
    """
    Human-friendly semantic title.

    This is convenience metadata only. The raw class/reference information is
    still exported and remains authoritative.
    """

    class_name = (
        class_path.rsplit(".", 1)[-1]
        if class_path
        else ""
    )

    props = _property_map(
        properties
    )

    if class_name == "K2Node_CallFunction":

        name = _member_name(
            props.get(
                "FunctionReference"
            )
        )

        return (
            name
            or "Call Function"
        )

    if class_name == "K2Node_VariableGet":

        name = _member_name(
            props.get(
                "VariableReference"
            )
        )

        return (
            "Get {}".format(name)
            if name
            else "Variable Get"
        )

    if class_name == "K2Node_VariableSet":

        name = _member_name(
            props.get(
                "VariableReference"
            )
        )

        return (
            "Set {}".format(name)
            if name
            else "Variable Set"
        )

    if class_name == "K2Node_Event":

        name = _member_name(
            props.get(
                "EventReference"
            )
        )

        return (
            "Event {}".format(name)
            if name
            else "Event"
        )

    if class_name == "K2Node_FunctionEntry":

        name = (
            _member_name(
                props.get(
                    "FunctionReference"
                )
            )
            or _decode_scalar(
                props.get(
                    "CustomGeneratedFunctionName",
                    ""
                )
            )
        )

        return (
            name
            or "Function Entry"
        )

    if class_name == "K2Node_FunctionResult":
        return "Return"

    if class_name == "K2Node_IfThenElse":
        return "Branch"

    if class_name == "K2Node_Knot":
        return "Reroute"

    if class_name == "K2Node_DynamicCast":

        target_type = _decode_scalar(
            props.get(
                "TargetType",
                ""
            )
        )

        return (
            "Cast To {}".format(target_type)
            if target_type
            else "Dynamic Cast"
        )

    if class_name == "K2Node_MacroInstance":

        macro = _parse_reference(
            props.get(
                "MacroGraphReference"
            )
        )

        if isinstance(
            macro,
            dict
        ):

            macro_graph = macro.get(
                "MacroGraph"
            )

            if macro_graph:
                return "Macro {}".format(
                    macro_graph
                )

        return "Macro"

    return (
        class_name
        or "Node"
    )


def _parse_node(obj):
    props = _property_map(
        obj.properties
    )

    references = {}

    reference_properties = {
        "FunctionReference": "function",
        "VariableReference": "variable",
        "EventReference": "event",
        "MacroGraphReference": "macro",
        "DelegateReference": "delegate",
    }

    for property_name, output_name in reference_properties.items():

        if property_name in props:

            references[
                output_name
            ] = _parse_reference(
                props[property_name]
            )

    selected_properties = {}

    for property_name in (
        "TargetType",
        "Enum",
        "CustomGeneratedFunctionName",
        "ExtraFlags",
        "bOverrideFunction"
    ):

        if property_name in props:

            selected_properties[
                property_name
            ] = _decode_scalar(
                props[property_name]
            )

    pins = [
        _parse_pin(line)
        for line in obj.properties
        if line.startswith(
            "CustomProperties Pin "
        )
    ]

    return {
        "name": obj.name,

        "class": obj.class_path,

        "guid": _decode_scalar(
            props.get(
                "NodeGuid",
                ""
            )
        ) or None,

        "title": _node_title(
            obj.class_path,
            obj.properties
        ),

        "position": {
            "x": _decode_scalar(
                props.get(
                    "NodePosX",
                    "0"
                )
            ),

            "y": _decode_scalar(
                props.get(
                    "NodePosY",
                    "0"
                )
            ),
        },

        "comment": _decode_scalar(
            props.get(
                "NodeComment",
                ""
            )
        ) or None,

        "enabled_state": _decode_scalar(
            props.get(
                "EnabledState",
                "Enabled"
            )
        ),

        "is_intermediate": bool(
            _decode_scalar(
                props.get(
                    "bIsIntermediateNode",
                    "False"
                )
            )
        ),

        "references": references,

        "properties": selected_properties,

        "pins": pins,
    }


# ============================================================================
# Graphs / connections
# ============================================================================


def _extract_graph_lists(root):
    result = {
        "event": [],
        "function": [],
        "macro": [],
        "delegate": [],
    }

    source_properties = {
        "UbergraphPages": "event",
        "FunctionGraphs": "function",
        "MacroGraphs": "macro",
        "DelegateSignatureGraphs": "delegate",
    }

    for line in root.properties:

        for prefix, kind in source_properties.items():

            if not line.startswith(
                prefix + "("
            ):
                continue

            _, raw_value = line.split(
                "=",
                1
            )

            reference = _decode_scalar(
                raw_value
            )

            graph_name = None

            if isinstance(
                reference,
                str
            ):

                match = re.search(
                    r"'([^']+)'$",
                    reference
                )

                if match:

                    graph_name = (
                        match.group(1)
                        .split(":")[-1]
                    )

            if graph_name:

                result[
                    kind
                ].append(
                    graph_name
                )

    return result


def _graph_kind(
    graph_name,
    graph_lists
):
    for kind, names in graph_lists.items():

        if graph_name in names:
            return kind

    # Graphs emitted by the compiled Blueprint but absent from the authored
    # graph lists are treated as generated/intermediate source.
    return "generated"


def _build_connections(nodes):
    pin_index = {}

    for node in nodes:

        for pin in node["pins"]:

            pin_index[
                (
                    node["name"],
                    pin["id"]
                )
            ] = {
                "node": node,
                "pin": pin,
            }

    connections = []

    seen_pairs = set()

    for node in nodes:

        for pin in node["pins"]:

            for link in pin["links"]:

                if (
                    "node" not in link
                    or "pin_id" not in link
                ):
                    continue

                local_key = (
                    node["name"],
                    pin["id"]
                )

                remote_key = (
                    link["node"],
                    link["pin_id"]
                )

                pair_key = tuple(
                    sorted(
                        (
                            local_key,
                            remote_key
                        )
                    )
                )

                # LinkedTo is serialized on both pins.
                # Collapse the pair into one canonical connection.
                if pair_key in seen_pairs:
                    continue

                seen_pairs.add(
                    pair_key
                )

                remote = pin_index.get(
                    remote_key
                )

                if pin["direction"] == "output":

                    source_node = node
                    source_pin = pin

                    target_node = (
                        remote["node"]
                        if remote
                        else None
                    )

                    target_pin = (
                        remote["pin"]
                        if remote
                        else None
                    )

                elif (
                    remote
                    and remote["pin"]["direction"] == "output"
                ):

                    source_node = remote["node"]
                    source_pin = remote["pin"]

                    target_node = node
                    target_pin = pin

                else:

                    # Defensive fallback for unusual pin schemas.
                    source_node = node
                    source_pin = pin

                    target_node = (
                        remote["node"]
                        if remote
                        else None
                    )

                    target_pin = (
                        remote["pin"]
                        if remote
                        else None
                    )

                connection_kind = (
                    "exec"
                    if (
                        source_pin["type"]["category"] == "exec"
                        or (
                            target_pin
                            and target_pin["type"]["category"] == "exec"
                        )
                    )
                    else "data"
                )

                connections.append({
                    "kind": connection_kind,

                    "from": {
                        "node": source_node["name"],
                        "pin_id": source_pin["id"],
                        "pin_name": source_pin["name"],
                    },

                    "to": {
                        "node": (
                            target_node["name"]
                            if target_node
                            else link["node"]
                        ),

                        "pin_id": (
                            target_pin["id"]
                            if target_pin
                            else link["pin_id"]
                        ),

                        "pin_name": (
                            target_pin["name"]
                            if target_pin
                            else None
                        ),
                    },
                })

    connections.sort(
        key=lambda connection: (
            connection["from"]["node"],
            str(
                connection["from"]["pin_name"]
            ),
            connection["to"]["node"],
            str(
                connection["to"]["pin_name"]
            ),
        )
    )

    return connections


def _parse_graph(
    obj,
    kind
):
    props = _property_map(
        obj.properties
    )

    nodes = [
        _parse_node(child)
        for child in obj.children
    ]

    connections = _build_connections(
        nodes
    )

    pin_count = sum(
        len(node["pins"])
        for node in nodes
    )

    return {
        "schema_version": 1,

        "graph": {
            "name": obj.name,
            "kind": kind,

            "guid": _decode_scalar(
                props.get(
                    "GraphGuid",
                    ""
                )
            ) or None,
        },

        "stats": {
            "node_count": len(nodes),
            "pin_count": pin_count,

            "connection_count": len(
                connections
            ),

            "exec_connection_count": sum(
                1
                for connection in connections
                if connection["kind"] == "exec"
            ),

            "data_connection_count": sum(
                1
                for connection in connections
                if connection["kind"] == "data"
            ),
        },

        "nodes": nodes,

        "connections": connections,
    }


# ============================================================================
# Public parser
# ============================================================================


def parse_blueprint_text(text):
    roots = _parse_object_tree(
        text
    )

    if len(roots) != 1:

        raise ValueError(
            "Expected exactly one root UObject in Blueprint T3D; found {}."
            .format(
                len(roots)
            )
        )

    root = roots[0]

    graph_lists = _extract_graph_lists(
        root
    )

    detailed_graph_objects = [
        child
        for child in root.children
        if (
            child.class_path
            and child.class_path.endswith(
                ".EdGraph"
            )
            and not child.explicit_class
        )
    ]

    graph_documents = [
        _parse_graph(
            graph_object,
            _graph_kind(
                graph_object.name,
                graph_lists
            )
        )
        for graph_object in detailed_graph_objects
    ]

    authored_graphs = [
        document
        for document in graph_documents
        if document["graph"]["kind"] != "generated"
    ]

    generated_graphs = [
        document
        for document in graph_documents
        if document["graph"]["kind"] == "generated"
    ]

    variables = [
        _parse_variable(line)
        for line in root.properties
        if line.startswith(
            "NewVariables("
        )
    ]

    variables.sort(
        key=lambda variable: (
            str(
                variable.get(
                    "name",
                    ""
                )
            ).lower()
        )
    )

    root_props = _property_map(
        root.properties
    )

    index = {
        "schema_version": 1,

        "blueprint": {
            "name": root.name,
            "class": root.class_path,

            "guid": _decode_scalar(
                root_props.get(
                    "BlueprintGuid",
                    ""
                )
            ) or None,

            "parent_class": _decode_scalar(
                root_props.get(
                    "ParentClass",
                    ""
                )
            ) or None,
        },

        "variables": variables,

        "graphs": [
            {
                "name": document["graph"]["name"],
                "kind": document["graph"]["kind"],
                "guid": document["graph"]["guid"],
                **document["stats"],
            }
            for document in authored_graphs
        ],

        # Keep generated graph names/stats in the index for diagnostics, but
        # Commit 3 does not emit them as normal source graph files.
        "generated_graphs": [
            {
                "name": document["graph"]["name"],
                "guid": document["graph"]["guid"],
                **document["stats"],
            }
            for document in generated_graphs
        ],

        "stats": {
            "authored_graph_count": len(
                authored_graphs
            ),

            "generated_graph_count": len(
                generated_graphs
            ),

            "authored_node_count": sum(
                document["stats"]["node_count"]
                for document in authored_graphs
            ),

            "authored_pin_count": sum(
                document["stats"]["pin_count"]
                for document in authored_graphs
            ),

            "authored_connection_count": sum(
                document["stats"]["connection_count"]
                for document in authored_graphs
            ),

            "generated_node_count": sum(
                document["stats"]["node_count"]
                for document in generated_graphs
            ),

            "generated_pin_count": sum(
                document["stats"]["pin_count"]
                for document in generated_graphs
            ),
        },
    }

    return {
        "index": index,
        "authored_graphs": authored_graphs,
        "generated_graphs": generated_graphs,
    }


def parse_blueprint_file(filename):
    text, encoding = (
        text_io.read_unreal_text_file(
            filename
        )
    )

    if not text.strip():

        raise ValueError(
            "Blueprint T3D is empty: {}".format(
                filename
            )
        )

    try:

        return parse_blueprint_text(
            text
        )

    except ValueError as error:

        # Give us a useful diagnostic if another unusual Unreal text format
        # appears later in the 184-Blueprint sweep.
        preview = (
            text[:200]
            .replace("\r", "\\r")
            .replace("\n", "\\n")
        )

        raise ValueError(
            "{} "
            "[encoding={}, first_text={!r}]"
            .format(
                error,
                encoding,
                preview
            )
        )



# ============================================================================
# Parser diagnostics
# ============================================================================


def _walk_objects(obj, parent=None):
    """
    Recursively yield every T3D UObject block.

    Returns:
        (object, parent)
    """

    yield obj, parent

    for child in obj.children:

        for result in _walk_objects(
            child,
            obj
        ):
            yield result


def _is_graph_node_object(obj):
    """
    True for Blueprint graph node UObject classes.
    """

    if not obj.class_path:
        return False

    class_name = obj.class_path.rsplit(
        ".",
        1
    )[-1]

    return (
        class_name.startswith("K2Node_")
        or class_name.startswith("AnimGraphNode_")
        or class_name.startswith("EdGraphNode")
    )


def diagnose_node_coverage(filename):
    """
    Compare all detailed node objects present in raw T3D against the nodes
    currently consumed by our normalized graph parser.

    This lets us identify nested/special graphs without guessing.
    """

    text, encoding = (
        text_io.read_unreal_text_file(
            filename
        )
    )

    roots = _parse_object_tree(
        text
    )

    if len(roots) != 1:

        raise ValueError(
            "Expected one Blueprint root; found {}."
            .format(
                len(roots)
            )
        )

    root = roots[0]

    # ------------------------------------------------------------------------
    # All detailed node UObject blocks anywhere in the Blueprint
    # ------------------------------------------------------------------------

    all_detailed_nodes = {}

    node_parents = {}

    for obj, parent in _walk_objects(
        root
    ):

        if (
            _is_graph_node_object(obj)
            and not obj.explicit_class
        ):

            key = (
                obj.export_path
                or "{}:{}".format(
                    parent.name if parent else "?",
                    obj.name
                )
            )

            all_detailed_nodes[key] = obj

            node_parents[key] = (
                parent.name
                if parent
                else None
            )

    # ------------------------------------------------------------------------
    # Nodes currently consumed by our parser
    #
    # This intentionally matches the current Commit-3 implementation.
    # ------------------------------------------------------------------------

    current_graphs = [
        child
        for child in root.children
        if (
            child.class_path
            and child.class_path.endswith(
                ".EdGraph"
            )
            and not child.explicit_class
        )
    ]

    consumed_nodes = {}

    for graph in current_graphs:

        for node in graph.children:

            if not _is_graph_node_object(
                node
            ):
                continue

            key = (
                node.export_path
                or "{}:{}".format(
                    graph.name,
                    node.name
                )
            )

            consumed_nodes[key] = node

    # ------------------------------------------------------------------------
    # Difference
    # ------------------------------------------------------------------------

    missing_keys = sorted(
        set(all_detailed_nodes.keys())
        -
        set(consumed_nodes.keys())
    )

    missing = []

    for key in missing_keys:

        node = all_detailed_nodes[
            key
        ]

        missing.append({
            "name": node.name,

            "class": node.class_path,

            "export_path": node.export_path,

            "parent_object": node_parents.get(
                key
            ),
        })

    result = {
        "encoding": encoding,

        "all_detailed_node_count": len(
            all_detailed_nodes
        ),

        "currently_consumed_node_count": len(
            consumed_nodes
        ),

        "missing_node_count": len(
            missing
        ),

        "missing_nodes": missing,
    }

    return result