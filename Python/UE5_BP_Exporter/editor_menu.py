"""Editor menu for standalone Audit, Full Export and Open Export Folder."""

import os
import subprocess
import sys
import traceback

import unreal

OWNER_NAME = "UE5BlueprintExporter"
TOOLS_MENU_NAME = "LevelEditor.MainMenu.Tools"
SECTION_NAME = "BlueprintExporter"
SUBMENU_NAME = "BlueprintExporter"
SUBMENU_MENU_NAME = "{}.{}".format(TOOLS_MENU_NAME, SUBMENU_NAME)
COMMAND_SECTION_NAME = "BlueprintExporterCommands"


def _execute(command_name, callback):
    try:
        unreal.log("[UE5_BP_Exporter] {}".format(command_name))
        return callback()
    except Exception:
        unreal.log_error(
            "[UE5_BP_Exporter] {} failed.\n{}".format(
                command_name, traceback.format_exc()
            )
        )
        raise


def audit_project():
    from UE5_BP_Exporter import audit
    return _execute("Audit Project", audit.run)


def export_project():
    from UE5_BP_Exporter import export_context
    # Existing full exporter already performs discovery, then applies strict
    # REVIEW + metadata safety gates before graph and structural extraction.
    return _execute("Full Export", export_context.run)


def export_ai_context():
    """Retain console compatibility with the old menu entry point."""
    return export_project()


def open_context_folder():
    from UE5_BP_Exporter import io_utils
    folder = os.path.abspath(io_utils.get_output_root())
    if os.name == "nt":
        os.startfile(folder)
    else:
        opener = "open" if sys.platform == "darwin" else "xdg-open"
        subprocess.Popen([opener, folder])


def _make_python_entry(name, label, tooltip, function_name):
    entry = unreal.ToolMenuEntry(
        name=name,
        type=unreal.MultiBlockType.MENU_ENTRY,
    )
    entry.set_label(label)
    entry.set_tool_tip(tooltip)
    entry.set_string_command(
        unreal.ToolMenuStringCommandType.PYTHON,
        "",
        "import UE5_BP_Exporter.editor_menu as _bp_menu; "
        "_bp_menu.{}()".format(function_name),
    )
    return entry


def unregister():
    menus = unreal.ToolMenus.get()
    try:
        menus.unregister_owner_by_name(OWNER_NAME)
    except Exception:
        pass
    try:
        if menus.is_menu_registered(SUBMENU_MENU_NAME):
            menus.remove_menu(SUBMENU_MENU_NAME)
    except Exception:
        pass
    menus.refresh_all_widgets()


def register():
    """Tools > Blueprint Exporter > Audit / Full Export / Open Folder."""
    menus = unreal.ToolMenus.get()
    unregister()

    tools_menu = menus.extend_menu(TOOLS_MENU_NAME)
    tools_menu.add_section(SECTION_NAME)
    submenu = tools_menu.add_sub_menu(
        OWNER_NAME,
        SECTION_NAME,
        SUBMENU_NAME,
        "Blueprint Exporter",
        "Read-only Unreal project audit and source export",
    )
    submenu.add_section(COMMAND_SECTION_NAME)

    commands = (
        (
            "AuditProject",
            "Audit Project",
            "Discover and classify assets; do not clear previous exports.",
            "audit_project",
        ),
        (
            "FullExport",
            "Full Export",
            "Run fresh discovery, then export metadata, graphs and structural assets.",
            "export_project",
        ),
        (
            "OpenFolder",
            "Open Export Folder",
            "Open Blueprint_Context (or your configured output folder).",
            "open_context_folder",
        ),
    )
    for name, label, tooltip, function_name in commands:
        submenu.add_menu_entry(
            COMMAND_SECTION_NAME,
            _make_python_entry(
                "BlueprintExporter." + name, label, tooltip, function_name
            ),
        )
    menus.refresh_all_widgets()
    unreal.log(
        "[UE5_BP_Exporter] Registered menu: Tools > Blueprint Exporter"
    )
