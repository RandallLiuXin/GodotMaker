"""The ``single`` to ``Texture2D`` route, served by Godot's default import.

Godot already imports a plain image file as a ``Texture2D``, so this route
writes nothing: the compiled artifact *is* the source image. It exists so the
pair is a registered, receipted, validated outcome instead of an unregistered
combination, and so the generic registry checks — stable-path containment and
artifact existence — still run for it.

v1 adds no texture-import profile system. Import settings stay Godot's defaults
plus the project-wide pixel-art baseline; per-texture mipmap, repeat,
compression, and filtering choices remain worker decisions.
"""
from __future__ import annotations

from typing import Any

from .contract import CompileRequest, CompilerError
from .registry import CompilerRegistry, CompilerRoute

COMPILER_ID = "texture2d_default_import"
COMPILER_VERSION = 1


def compile_texture2d(request: CompileRequest) -> dict[str, Any]:
    """Confirm the artifact is the default-imported source image itself."""
    if request.artifact_path != request.source_path:
        raise CompilerError(
            "a Texture2D artifact is the default-imported source image, so "
            f"artifact_path must equal source_path; got {request.artifact_path} "
            f"instead of {request.source_path}"
        )
    return {"mode": "godot_default_import"}


def register_into(registry: CompilerRegistry) -> CompilerRoute:
    """Register this route on ``registry``."""
    return registry.register(
        source_layout_type="single",
        artifact_type="Texture2D",
        compiler_id=COMPILER_ID,
        compiler_version=COMPILER_VERSION,
        compiler=compile_texture2d,
    )
