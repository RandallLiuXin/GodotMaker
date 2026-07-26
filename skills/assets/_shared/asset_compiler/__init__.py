"""Shared Godot artifact compiler interface and registry for asset skills.

See ``godot-artifact-compiler-contract.md`` next to this package for the
contract this code implements. Concrete family compilers (``AtlasTexture``,
``SpriteFrames``, ``Theme``, ``StyleBoxTexture``, ``TileSet``) live outside the
registry and register themselves into it.

There is deliberately no module-level default registry instance. A caller builds
one with :func:`build_default_registry` and every family compiler for that run
registers into that instance. A process-global would let one caller's
registrations be invisible to a second caller holding a freshly built registry,
and — because ``register()`` rejects a duplicate pair outright — would turn a
re-imported self-registering module into an import-time crash.
"""
from __future__ import annotations

from . import atlas_texture, sprite_frames, stylebox_texture, texture2d, theme
from .contract import (
    CompileReceipt,
    CompileRequest,
    CompileResult,
    CompilerError,
    GodotArtifact,
    require_text,
)
from .registry import (
    SOURCE_IS_ARTIFACT_TYPES,
    Compiler,
    CompilerRegistry,
    CompilerRoute,
    is_same_file,
)


def build_default_registry() -> CompilerRegistry:
    """Return a new registry holding every compiler the shared layer ships."""
    registry = CompilerRegistry()
    texture2d.register_into(registry)
    atlas_texture.register_into(registry)
    sprite_frames.register_into(registry)
    stylebox_texture.register_into(registry)
    return registry


__all__ = [
    "SOURCE_IS_ARTIFACT_TYPES",
    "CompileReceipt",
    "CompileRequest",
    "CompileResult",
    "Compiler",
    "CompilerError",
    "CompilerRegistry",
    "CompilerRoute",
    "GodotArtifact",
    "build_default_registry",
    "is_same_file",
    "require_text",
    "atlas_texture",
    "sprite_frames",
    "stylebox_texture",
    "texture2d",
    "theme",
]
