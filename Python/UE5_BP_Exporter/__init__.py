"""Project-independent Unreal Blueprint source exporter.

Legacy source modules reference `CodeXAI`. Preserve that import name as an
alias of this package to avoid changing the extraction/parsing implementation.
This compatibility alias may be removed after an optional future cleanup.
"""

import sys

EXPORTER_VERSION = "0.5.0"

# Set before any exporter submodule imports occur.
sys.modules.setdefault("CodeXAI", sys.modules[__name__])
