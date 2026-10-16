"""Unreal startup entry point; copy to <Project>/Content/Python/init_unreal.py."""

try:
    from UE5_BP_Exporter import editor_menu
    editor_menu.register()
except Exception:
    import traceback
    import unreal
    unreal.log_error(
        "[UE5_BP_Exporter] Unable to register Tools menu.\n{}".format(
            traceback.format_exc()
        )
    )
