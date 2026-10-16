import json
import os
import shutil

import unreal

from CodeXAI import config


# ============================================================================
# Output paths
# ============================================================================

def get_output_root():
    external_root = getattr(
        config,
        "EXTERNAL_OUTPUT_ROOT",
        None
    )

    if external_root:
        output_root = os.path.abspath(
            os.path.expanduser(
                external_root
            )
        )

    else:
        saved_directory = (
            unreal.Paths.project_saved_dir()
        )

        output_root = os.path.join(
            saved_directory,
            config.OUTPUT_FOLDER_NAME
        )

        output_root = os.path.abspath(
            output_root
        )

    os.makedirs(
        output_root,
        exist_ok=True
    )

    return output_root


def get_mirror_root():
    return os.path.join(
        get_output_root(),
        config.MIRROR_FOLDER_NAME
    )

def ensure_output_root():
    """
    Ensure the generated export directory exists.
    """

    output_root = get_output_root()

    os.makedirs(
        output_root,
        exist_ok=True
    )

    return output_root


def recreate_mirror_root():
    """
    Delete and recreate ONLY the generated CodeX_Restruct mirror.

    We deliberately do not delete the entire CodeX_AI_Context folder because
    discovery_manifest.json and other top-level reports live beside it.

    This only touches:
        <Project>/Saved/CodeX_AI_Context/CodeX_Restruct
    """

    mirror_root = os.path.normpath(
        get_mirror_root()
    )

    output_root = os.path.normpath(
        get_output_root()
    )

    # Defensive guard:
    # never allow an accidental delete outside our generated output folder.
    if not mirror_root.startswith(output_root):
        raise RuntimeError(
            "Refusing to clear mirror outside CodeX AI output root: {}".format(
                mirror_root
            )
        )

    if os.path.isdir(mirror_root):
        shutil.rmtree(mirror_root)

    os.makedirs(
        mirror_root,
        exist_ok=True
    )

    return mirror_root


# ============================================================================
# JSON
# ============================================================================


def write_json(path, data):
    """
    Deterministic human-readable JSON.
    """

    parent = os.path.dirname(path)

    if parent:
        os.makedirs(
            parent,
            exist_ok=True
        )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
            sort_keys=False
        )


def asset_output_directory(relative_package):
    """
    Example:

        Frameworks/PlayerFramework/Core/BP_PlayerBase

    becomes:

        Saved/CodeX_AI_Context/
            CodeX_Restruct/
                Frameworks/
                    PlayerFramework/
                        Core/
                            BP_PlayerBase/
    """

    relative_package = relative_package.replace(
        "/",
        os.sep
    )

    return os.path.join(
        get_mirror_root(),
        relative_package
    )