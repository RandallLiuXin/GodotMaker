"""Shared Godot artifact compiler interface and registry for asset skills.

See ``godot-artifact-compiler-contract.md`` next to this package for the
contract this code implements. Concrete family compilers (``AtlasTexture``,
``SpriteFrames``, ``Theme``, ``StyleBoxTexture``, ``TileSet``) live outside the
registry and register themselves into it.
"""
from __future__ import annotations

from . import texture2d
from .contract import (
    CompileReceipt,
    CompileRequest,
    CompileResult,
    CompilerError,
    GodotArtifact,
    require_text,
)
from .registry import Compiler, CompilerRegistry, CompilerRoute


def build_default_registry() -> CompilerRegistry:
    """Return a registry holding every compiler the shared layer ships."""
    registry = CompilerRegistry()
    texture2d.register_into(registry)
    return registry


DEFAULT_REGISTRY = build_default_registry()

__all__ = [
    "DEFAULT_REGISTRY",
    "CompileReceipt",
    "CompileRequest",
    "CompileResult",
    "Compiler",
    "CompilerError",
    "CompilerRegistry",
    "CompilerRoute",
    "GodotArtifact",
    "build_default_registry",
    "require_text",
    "texture2d",
]
