import os
import traceback

import unreal


# ============================================================================
# Menu constants
# ============================================================================


OWNER_NAME = "CodeXAI"

TOOLS_MENU_NAME = "LevelEditor.MainMenu.Tools"

SECTION_NAME = "CodeXAI"
SUBMENU_NAME = "CodeXAI"
SUBMENU_MENU_NAME = "{}.{}".format(
    TOOLS_MENU_NAME,
    SUBMENU_NAME
)

COMMAND_SECTION_NAME = "CodeXAICommands"


# ============================================================================
# Commands
# ============================================================================


def export_ai_context():
    """
    Run the normal CodeX AI context exporter.

    This remains synchronous on purpose: Unreal asset/editor APIs are expected
    to run on the editor thread, and this command should behave exactly like
    calling CodeXAI.export_context.run() from the Python console.
    """

    unreal.log(
        "[CodeXAI] Menu command: Export AI Context"
    )

    try:
        from CodeXAI import export_context

        export_context.run()

    except Exception:
        unreal.log_error(
            "[CodeXAI] Export AI Context failed.\n{}".format(
                traceback.format_exc()
            )
        )
        raise


def open_context_folder():
    """
    Open the configured CodeX AI context repository/output directory.

    No Git command is executed. This only asks Windows Explorer to open the
    folder already configured through CodeXAI.io_utils/config.
    """

    from CodeXAI import io_utils

    output_root = os.path.abspath(
        io_utils.get_output_root()
    )

    if not os.path.isdir(
        output_root
    ):
        unreal.log_error(
            "[CodeXAI] Output folder does not exist: {}".format(
                output_root
            )
        )
        return

    unreal.log(
        "[CodeXAI] Opening context folder: {}".format(
            output_root
        )
    )

    try:
        os.startfile(
            output_root
        )

    except Exception:
        unreal.log_error(
            "[CodeXAI] Could not open context folder.\n{}".format(
                traceback.format_exc()
            )
        )
        raise


# ============================================================================
# Menu construction
# ============================================================================


def _make_python_entry(
    name,
    label,
    tool_tip,
    command
):
    entry = unreal.ToolMenuEntry(
        name=name,
        type=unreal.MultiBlockType.MENU_ENTRY
    )

    entry.set_label(
        label
    )

    entry.set_tool_tip(
        tool_tip
    )

    entry.set_string_command(
        unreal.ToolMenuStringCommandType.PYTHON,
        "",
        command
    )

    return entry


def unregister():
    """
    Remove this tool's menu registrations.

    Useful while iterating on editor_menu.py in a live editor session.
    """

    menus = unreal.ToolMenus.get()

    try:
        menus.unregister_owner_by_name(
            OWNER_NAME
        )
    except Exception:
        pass

    # Defensive cleanup for live Python reloads. Normally unregistering the
    # owner is enough, but explicitly remove the generated submenu if UE still
    # has it registered from an earlier version of the script.
    try:
        if menus.is_menu_registered(
            SUBMENU_MENU_NAME
        ):
            menus.remove_menu(
                SUBMENU_MENU_NAME
            )
    except Exception:
        pass

    menus.refresh_all_widgets()


def register():
    """
    Register:

        Tools
        └── CodeX AI
            ├── Export AI Context
            └── Open Context Folder
    """

    menus = unreal.ToolMenus.get()

    # Keep registration idempotent during development/reloads.
    unregister()

    # extend_menu() is intentionally used here instead of requiring the Tools
    # menu to already exist. UE ToolMenus allows extending a menu before its UI
    # has been generated.
    tools_menu = menus.extend_menu(
        TOOLS_MENU_NAME
    )

    tools_menu.add_section(
        SECTION_NAME
    )

    code_x_menu = tools_menu.add_sub_menu(
        OWNER_NAME,
        SECTION_NAME,
        SUBMENU_NAME,
        "CodeX AI",
        "CodeX AI read-only project context tools."
    )

    code_x_menu.add_section(
        COMMAND_SECTION_NAME
    )

    export_entry = _make_python_entry(
        "CodeXAI.ExportAIContext",
        "Export AI Context",
        "Regenerate the AI-readable CodeX project representation.",
        (
            "import CodeXAI.editor_menu as _codex_menu; "
            "_codex_menu.export_ai_context()"
        )
    )

    open_entry = _make_python_entry(
        "CodeXAI.OpenContextFolder",
        "Open Context Folder",
        "Open the local CodeX AI context repository/output folder.",
        (
            "import CodeXAI.editor_menu as _codex_menu; "
            "_codex_menu.open_context_folder()"
        )
    )

    code_x_menu.add_menu_entry(
        COMMAND_SECTION_NAME,
        export_entry
    )

    code_x_menu.add_menu_entry(
        COMMAND_SECTION_NAME,
        open_entry
    )

    menus.refresh_all_widgets()

    unreal.log(
        "[CodeXAI] Editor menu registered: Tools > CodeX AI"
    )
