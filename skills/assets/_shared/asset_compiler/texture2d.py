"""The ``single`` to ``Texture2D`` route, served by Godot's default import.

Godot already imports a plain image file as a ``Texture2D``, so this route
writes nothing: the compiled artifact *is* the source image. It exists so the
pair is a registered, receipted, validated outcome instead of an unregistered
combination, and so the generic registry checks — stable-path containment and
artifact existence — still run for it.

It registers with ``writes_artifact=False``, which is what makes
``artifact_path == source_path`` legal here and rejected everywhere else. The
registry enforces both halves of that rule; this module only has to declare
which side it is on.

v1 adds no texture-import profile system. Import settings stay Godot's defaults;
per-texture mipmap, repeat, compression, and filtering choices remain worker
decisions.
"""
from __future__ import annotations

from typing import Any

from .contract import CompileRequest, CompilerError
from .registry import CompilerRegistry, CompilerRoute

COMPILER_ID = "texture2d_default_import"
COMPILER_VERSION = 1


def compile_texture2d(request: CompileRequest) -> dict[str, Any]:
    """Record that Godot's default import already produced the artifact."""
    if request.artifact_path != request.source_path:
        raise CompilerError(
            "texture2d_default_import writes no file, so artifact_path must equal "
            "source_path"
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
        writes_artifact=False,
    )
