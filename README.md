# UE5 Blueprint Exporter — Generic Project Update v0.5.0

This ZIP contains the **replacement Python source files** for the existing
[UE5_BlueprintExporter_Python](https://github.com/nitrous-git/UE5_BlueprintExporter_Python)
repository. No updater, patch, or installer script is included.

## Apply to your existing Git repository

Extract the contents of this archive into the **root of your existing repository**,
allowing files of the same name to be replaced. All other repository files stay
untouched. In particular, the original `metadata_exporter.py`, graph parsers,
raw T3D exporter, and structural serializers remain in place and are required.

The package deliberately contains **only added/replaced source files** rather
than unrelated binaries, caches, or an installer. Do not delete the original
`Python/UE5_BP_Exporter/graphs/` or `structural/` directories.

Then commit and push the changes to your main branch yourself.

## Install in a new Unreal Engine project

1. Enable **Python Editor Script Plugin** in Edit > Plugins; restart Unreal.
2. Copy `Python/init_unreal.py` from the updated repository into
   `<YourProject>/Content/Python/init_unreal.py`.
3. Copy the **entire** `Python/UE5_BP_Exporter` directory from the updated
   repository into `<YourProject>/Content/Python/UE5_BP_Exporter`.
4. Restart Unreal Editor.
5. Navigate to **Tools > Blueprint Exporter**.

The menu exposes:

- **Audit Project** — classify project assets and generate `discovery_manifest.json`
  plus `discovery_candidates.txt`. It does **not** clear a previous export.
- **Full Export** — use the existing exporter pipeline: fresh discovery,
  safety checks, architecture metadata, Blueprint graphs, and structural data.
  Stops if unclassified REVIEW assets remain, as before.
- **Open Export Folder** — view the generated files.

### Default configuration

Edit `Python/UE5_BP_Exporter/config.py` when necessary:

```python
ROOT_PATH = "/Game"       # Prefer /Game/MyGame for a focused gameplay export
EXTERNAL_OUTPUT_ROOT = None
OUTPUT_FOLDER_NAME = "Blueprint_Context"
MIRROR_FOLDER_NAME = "Game"
EXCLUDED_PATHS = []
EXCLUDED_ASSETS = set()
DEPRECATED_NAME_MARKERS = ()
```

Outputs go to `<YourProject>/Saved/Blueprint_Context/` by default:

```text
Blueprint_Context/
  discovery_manifest.json
  discovery_candidates.txt
  export_manifest.json       # After successful full export
  Game/                      # Regenerated during full export
    ...
```

The `Game/` generated mirror is **cleared and recreated** by Full Export.
Do not put manually maintained files inside it. The tool does not edit Unreal
`.uasset` files.

## Architecture and compatibility

- Graph/parser, metadata, and structural-export algorithms are unchanged.
- Output manifest schemas and asset folder conventions are maintained, except
  for the now-configurable output root/mirror naming.
- `UE5_BP_Exporter/__init__.py` registers a compatibility alias for the legacy
  `CodeXAI` Python imports still present in original extraction modules. This
  avoids rewriting those working implementation files during this small update.
- The original full export still runs its discovery internally. Audit Project
  exposes the same discovery pass separately without duplicating full export.
- Existing project-specific exclusions must be copied into `config.py` if
  needed; generic defaults intentionally exclude nothing by path or name.

**Validation:** Replacement files pass Python syntax compilation. Discovery
classification and path behavior have been tested with a lightweight Unreal
API stub. The full UE Editor/T3D export cannot be executed outside Unreal and
should be tested with a small sample project before large exports.
