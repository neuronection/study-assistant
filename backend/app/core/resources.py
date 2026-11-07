"""Runtime resource locations (checkout, frozen bundle, container image).

Python packages are bundled into the PyInstaller archive, so module-relative
data reads only work when the data files are shipped as `datas` and resolved
from `sys._MEIPASS`. The container image keeps the checkout layout.
"""

from __future__ import annotations

import sys
from pathlib import Path


def contracts_dir() -> Path:
    """The vendored family contracts (`contracts/` at the repo root)."""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled) / "contracts"
    return Path(__file__).resolve().parents[3] / "contracts"
