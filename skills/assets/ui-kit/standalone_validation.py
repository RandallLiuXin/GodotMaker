"""Standalone UI Kit validation entry point."""
from __future__ import annotations

import sys
from pathlib import Path

_SHARED = Path(__file__).resolve().parents[1] / "_shared"
_TOOLS = Path(__file__).resolve().parents[3] / "tools"
for path in (str(_SHARED), str(_TOOLS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from ui_card_standalone_validation import UICardSkillError, compile_and_validate  # noqa: E402

__all__ = ["UICardSkillError", "compile_and_validate"]
