"""Safe output directory helpers shared by exporter stages."""

import json
import os
import shutil

import unreal
from CodeXAI import config


def _is_same_or_descendant(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def _real(path):
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


def get_output_root():
    custom = getattr(config, "EXTERNAL_OUTPUT_ROOT", None)
    if custom:
        root = os.path.abspath(os.path.expanduser(str(custom)))
    else:
        root = os.path.abspath(os.path.join(
            unreal.Paths.project_saved_dir(), config.OUTPUT_FOLDER_NAME
        ))

    # Never place generated JSON/T3D inside the Unreal content directory.
    content = _real(unreal.Paths.project_content_dir())
    if _is_same_or_descendant(_real(root), content):
        raise RuntimeError("Export output cannot be under project Content/: {}".format(root))

    os.makedirs(root, exist_ok=True)
    return root


def get_mirror_root():
    folder = str(config.MIRROR_FOLDER_NAME).strip()
    if not folder or folder in (".", "..") or os.path.isabs(folder):
        raise RuntimeError("MIRROR_FOLDER_NAME must be a simple folder name")
    if "/" in folder or "\\" in folder:
        raise RuntimeError("MIRROR_FOLDER_NAME cannot contain path separators")

    output_root = get_output_root()
    mirror_root = os.path.join(output_root, folder)
    if not _is_same_or_descendant(_real(mirror_root), _real(output_root)):
        raise RuntimeError("Unsafe export mirror path: {}".format(mirror_root))
    if _real(mirror_root) == _real(output_root):
        raise RuntimeError("Export mirror must differ from output root")
    return mirror_root


def ensure_output_root():
    return get_output_root()


def recreate_mirror_root():
    """Only clears the generated mirror, never top-level audit reports."""
    mirror_root = get_mirror_root()
    if os.path.isdir(mirror_root):
        shutil.rmtree(mirror_root)
    os.makedirs(mirror_root, exist_ok=True)
    return mirror_root


def write_json(path, data):
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    with open(path, "w", encoding="utf-8") as stream:
        json.dump(data, stream, indent=2, ensure_ascii=False, sort_keys=False)


def asset_output_directory(relative_package):
    """One asset package gets a folder beneath the generated mirror."""
    relative = str(relative_package).replace("\\", "/").strip("/")
    parts = relative.split("/") if relative else []
    if not parts or any(part in ("", ".", "..") for part in parts):
        raise ValueError("Invalid relative asset package path: {!r}".format(relative_package))
    dest = os.path.join(get_mirror_root(), *parts)
    if not _is_same_or_descendant(_real(dest), _real(get_mirror_root())):
        raise RuntimeError("Unsafe asset output directory: {}".format(dest))
    return dest
