import re

from CodeXAI.graphs import text_io


# ============================================================================
# Lightweight generic Unreal T3D object tree
# ============================================================================


class _ObjectBlock:
    def __init__(
        self,
        name=None,
        class_path=None,
        export_path=None
    ):
        self.name = name
        self.class_path = class_path
        self.export_path = export_path
        self.properties = []
        self.children = []


def _parse_header(line):
    text = line.strip()

    class_match = re.search(
        r"\bClass=([^\s]+)",
        text
    )

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

    # Detailed blocks often omit Class= but include:
    #
    #   ExportPath="/Script/Module.Type'/Game/...'"
    #
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
        export_path=export_path
    )


def _parse_tree(text):
    roots = []
    stack = []

    for source_line in text.splitlines():

        stripped = source_line.strip()

        if stripped.startswith("Begin Object"):

            obj = _parse_header(
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

            if stack:
                stack.pop()

        elif stack and stripped:

            stack[-1].properties.append(
                stripped
            )

    return roots


def _decode_simple(value):
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

    # Complex Unreal values intentionally remain as source text:
    #
    #   (X=1,Y=2)
    #   /Script/Engine.BlueprintGeneratedClass'...'
    #   NSLOCTEXT(...)
    #
    return value


def _property_records(lines):
    result = []

    for line in lines:

        if "=" in line:
            name, raw_value = line.split(
                "=",
                1
            )

            result.append({
                "name": name.strip(),
                "value": _decode_simple(
                    raw_value
                ),
            })

        else:

            result.append({
                "name": None,
                "value": line,
            })

    return result


def _to_document(obj):
    return {
        "name": obj.name,
        "class": obj.class_path,
        "export_path": obj.export_path,
        "properties": _property_records(
            obj.properties
        ),
        "children": [
            _to_document(child)
            for child in obj.children
        ],
    }


def parse_text(text):
    roots = _parse_tree(
        text
    )

    return [
        _to_document(root)
        for root in roots
    ]


def parse_file(filename):
    text, encoding = (
        text_io.read_unreal_text_file(
            filename
        )
    )

    return {
        "encoding": encoding,
        "roots": parse_text(
            text
        ),
    }
