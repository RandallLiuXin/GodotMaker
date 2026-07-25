"""Deterministic routing from a source layout and artifact type to a compiler.

A route is keyed by the ``(source_layout.type, godot_artifact.type)`` pair, not
by the layout alone: ``StyleBoxTexture`` is reachable from both ``single`` and
``region_atlas``, and ``single`` also compiles to ``Texture2D``. A one-to-one
layout-to-compiler map would reject those legal routes.

Registration is checked against the frozen ``LAYOUT_ARTIFACT_TYPES`` relation,
so a compiler cannot claim a pair the stable-entry schema would later refuse.
Everything else fails closed: an unregistered pair, a mismatched type, a missing
source, a compiler that raises, and a compiler that returns without writing its
artifact are all a :class:`CompilerError`.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Callable

from ._stable_entry import LAYOUT_ARTIFACT_TYPES
from .contract import (
    CompileReceipt,
    CompileRequest,
    CompileResult,
    CompilerError,
    GodotArtifact,
    require_text,
)

# A compiler produces its artifact on disk and returns its receipt details. It
# does not build the worker-facing artifact object; the registry does, so no
# compiler can widen the worker snapshot.
Compiler = Callable[[CompileRequest], Mapping[str, Any]]


@dataclass(frozen=True)
class CompilerRoute:
    """One registered ``(layout, artifact type)`` to compiler binding."""

    source_layout_type: str
    artifact_type: str
    compiler_id: str
    compiler_version: int
    compiler: Compiler

    @property
    def key(self) -> tuple[str, str]:
        return (self.source_layout_type, self.artifact_type)


class CompilerRegistry:
    """Holds the routes an asset skill may compile through."""

    def __init__(self) -> None:
        self._routes: dict[tuple[str, str], CompilerRoute] = {}

    def register(
        self,
        *,
        source_layout_type: str,
        artifact_type: str,
        compiler_id: str,
        compiler_version: int,
        compiler: Compiler,
    ) -> CompilerRoute:
        """Bind one compiler to one layout/artifact pair."""
        require_text(source_layout_type, "source_layout_type")
        require_text(artifact_type, "artifact_type")
        require_text(compiler_id, "compiler_id")
        allowed = LAYOUT_ARTIFACT_TYPES.get(source_layout_type)
        if allowed is None:
            raise CompilerError(
                f"source_layout_type compiles no Godot artifact: {source_layout_type}"
            )
        if artifact_type not in allowed:
            raise CompilerError(
                f"a {source_layout_type} source_layout may not compile to "
                f"{artifact_type}; allowed: {', '.join(allowed)}"
            )
        if type(compiler_version) is not int or compiler_version < 1:
            raise CompilerError("compiler_version must be a positive integer")
        if not callable(compiler):
            raise CompilerError("compiler must be callable")

        key = (source_layout_type, artifact_type)
        existing = self._routes.get(key)
        if existing is not None:
            raise CompilerError(
                f"{source_layout_type} -> {artifact_type} is already registered to "
                f"{existing.compiler_id}"
            )

        route = CompilerRoute(
            source_layout_type=source_layout_type,
            artifact_type=artifact_type,
            compiler_id=compiler_id,
            compiler_version=compiler_version,
            compiler=compiler,
        )
        self._routes[key] = route
        return route

    def routes(self) -> tuple[CompilerRoute, ...]:
        """Return every registered route, ordered by its routing key."""
        return tuple(self._routes[key] for key in sorted(self._routes))

    def resolve(self, source_layout_type: str, artifact_type: str) -> CompilerRoute:
        """Return the route for one pair, or fail closed."""
        route = self._routes.get((source_layout_type, artifact_type))
        if route is None:
            registered = ", ".join(
                f"{key[0]} -> {key[1]}" for key in sorted(self._routes)
            )
            raise CompilerError(
                f"no compiler is registered for {source_layout_type} -> "
                f"{artifact_type}; registered: {registered or 'none'}"
            )
        return route

    def compile(self, request: CompileRequest) -> CompileResult:
        """Validate, route, run one compiler, and receipt the result."""
        request.validate()
        route = self.resolve(request.source_layout_type, request.artifact_type)

        source_file = request.source_file()
        if not source_file.is_file():
            raise CompilerError(f"source_path not found: {request.source_path}")
        artifact_file = request.artifact_file()

        try:
            details = route.compiler(request)
        except CompilerError:
            raise
        except Exception as exc:  # noqa: BLE001 - surfaced as a compiler error
            raise CompilerError(f"{route.compiler_id} failed: {exc}") from exc

        if not isinstance(details, Mapping):
            raise CompilerError(
                f"{route.compiler_id} must return a mapping of receipt details"
            )
        if not artifact_file.is_file():
            raise CompilerError(
                f"{route.compiler_id} returned without writing {request.artifact_path}"
            )

        return CompileResult(
            godot_artifact=GodotArtifact(
                type=request.artifact_type,
                path=request.artifact_path,
            ),
            receipt=CompileReceipt(
                compiler_id=route.compiler_id,
                compiler_version=route.compiler_version,
                production_family=request.production_family,
                asset_id=request.asset_id,
                source_layout_type=request.source_layout_type,
                source_path=request.source_path,
                artifact_type=request.artifact_type,
                artifact_path=request.artifact_path,
                details=dict(details),
            ),
        )
