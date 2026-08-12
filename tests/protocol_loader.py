"""Load the pure protocol module without importing Home Assistant."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

MODULE_PATH = (
    Path(__file__).parents[1]
    / "custom_components"
    / "leeventus_ir"
    / "protocol.py"
)

SPEC = importlib.util.spec_from_file_location("leeventus_ir_protocol", MODULE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Unable to load protocol module from {MODULE_PATH}")

protocol = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = protocol
SPEC.loader.exec_module(protocol)
