# Project Python startup entry point.
#
# Unreal automatically executes Content/Python/init_unreal.py when the
# Python Editor Script Plugin starts.

try:
    import CodeXAI.editor_menu

    CodeXAI.editor_menu.register()

except Exception:
    import traceback
    import unreal

    unreal.log_error(
        "[CodeXAI] Failed to register editor menu.\n{}".format(
            traceback.format_exc()
        )
    )
