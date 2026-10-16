import os
import re

import unreal
from CodeXAI.graphs import text_io


# ============================================================================
# T3D export
# ============================================================================


def export_object_t3d(obj, filename):
    """
    Export one Unreal UObject to T3D text.

    READ-ONLY with respect to Unreal assets.

    The only write operation performed here is creation/overwrite of the
    external .t3d text file under Saved/CodeX_AI_Context.
    """

    if obj is None:
        return {
            "success": False,
            "filename": filename,
            "errors": ["Object is None."],
        }

    filename = os.path.normpath(filename)

    parent_directory = os.path.dirname(filename)

    if parent_directory:
        os.makedirs(
            parent_directory,
            exist_ok=True
        )

    # ------------------------------------------------------------------------
    # Explicit T3D text exporter
    # ------------------------------------------------------------------------

    exporter = unreal.ObjectExporterT3D()

    try:
        exporter.set_editor_property(
            "text",
            True
        )
    except Exception:
        pass

    # ------------------------------------------------------------------------
    # Export task
    # ------------------------------------------------------------------------

    task = unreal.AssetExportTask()

    task.set_editor_property(
        "object",
        obj
    )

    task.set_editor_property(
        "filename",
        filename
    )

    task.set_editor_property(
        "automated",
        True
    )

    task.set_editor_property(
        "prompt",
        False
    )

    task.set_editor_property(
        "replace_identical",
        True
    )

    task.set_editor_property(
        "selected",
        False
    )

    task.set_editor_property(
        "write_empty_files",
        False
    )

    task.set_editor_property(
        "exporter",
        exporter
    )

    # ------------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------------

    try:

        success = bool(
            unreal.Exporter.run_asset_export_task(
                task
            )
        )

    except Exception as error:

        return {
            "success": False,
            "filename": filename,
            "errors": [
                "Exporter exception: {}".format(
                    error
                )
            ],
        }

    try:
        task_errors = [
            str(error)
            for error in task.get_editor_property(
                "errors"
            )
        ]
    except Exception:
        task_errors = []

    file_exists = os.path.isfile(
        filename
    )

    file_size = (
        os.path.getsize(filename)
        if file_exists
        else 0
    )

    try:
        object_name = obj.get_name()
    except Exception:
        object_name = str(obj)

    try:
        object_class = obj.get_class().get_name()
    except Exception:
        object_class = None

    return {
        "success": success and file_exists,
        "filename": filename,
        "file_exists": file_exists,
        "file_size_bytes": file_size,
        "object_name": object_name,
        "object_class": object_class,
        "errors": task_errors,
    }


# ============================================================================
# T3D diagnostics
# ============================================================================


def inspect_t3d(filename):
    """
    Perform lightweight diagnostics on a raw T3D file.

    This is NOT the final parser.

    It tells us whether the serialization contains the information Commit 3
    needs before we build a real parser.
    """

    if not os.path.isfile(filename):

        return {
            "exists": False,
        }

    text, encoding = (
        text_io.read_unreal_text_file(
            filename
        )
    )

    # ------------------------------------------------------------------------
    # Common Blueprint text serialization markers
    # ------------------------------------------------------------------------

    node_begin_count = len(
        re.findall(
            r"Begin Object Class=.*?(?:K2Node_|AnimGraphNode_|EdGraphNode)",
            text
        )
    )

    custom_pin_count = text.count(
        "CustomProperties Pin"
    )

    linked_pin_count = text.count(
        "LinkedTo=("
    )

    node_guid_count = text.count(
        "NodeGuid="
    )

    pin_id_count = text.count(
        "PinId="
    )

    function_reference_count = text.count(
        "FunctionReference="
    )

    member_reference_count = text.count(
        "MemberName="
    )

    return {
        "exists": True,

        "encoding": encoding,

        "size_bytes": os.path.getsize(
            filename
        ),

        "line_count": (
            text.count("\n") + 1
        ),

        "markers": {
            "node_declarations": node_begin_count,
            "custom_properties_pin": custom_pin_count,
            "linked_to": linked_pin_count,
            "detailed_nodes": node_guid_count,
            "pin_id": pin_id_count,
            "function_reference": function_reference_count,
            "member_name": member_reference_count,
        },

        "contains_expected_graph_data": (
            node_begin_count > 0
            and
            custom_pin_count > 0
        ),
    }