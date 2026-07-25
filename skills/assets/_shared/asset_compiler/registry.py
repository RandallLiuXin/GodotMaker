"""Deterministic routing from a source layout and artifact type to a compiler.

A route is keyed by the ``(source_layout.type, godot_artifact.type)`` pair, not
by the layout alone: ``StyleBoxTexture`` is reachable from both ``single`` and
``region_atlas``, and ``single`` also compiles to ``Texture2D``. A one-to-one
layout-to-compiler map would reject those legal routes.

Registration is checked against the frozen ``LAYOUT_ARTIFACT_TYPES`` relation,
so a compiler cannot claim a pair the stable-entry schema would later refuse.
Everything else fails closed: an unregistered pair, a mismatched type, a missing
source, a compiler that raises, a compiler that publishes its source image as
the artifact, and a compiler that returns without rebuilding its artifact are
all a :class:`CompilerError`.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
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

# The artifact types Godot's default import already produces from the source
# file itself, and therefore the only ones a route may declare it writes no file
# for. Every other type must produce a new file at a path distinct from its
# source: a compiler that hands back its own source image is publishing a PNG as
# the resource a worker was promised -- "Declaring the source image as the
# artifact is the exact shortcut this mapping exists to reject"
# (tools/asset_stable_entry.py). Existence alone cannot catch that, because the
# source file satisfies it.
SOURCE_IS_ARTIFACT_TYPES = ("Texture2D",)


def _fingerprint(path: Path) -> tuple[int, int] | None:
    """Return a change marker for ``path``, or ``None`` when it is absent.

    Size alone misses a same-length rewrite and the modification time alone
    misses a rewrite inside the clock's resolution, so both are compared.
    Rewriting a file always advances ``st_mtime_ns``, so an unchanged marker
    means the compiler did not touch the artifact this run.
    """
    try:
        stat = path.stat()
    except OSError:
        return None
    return (stat.st_size, stat.st_mtime_ns)


@dataclass(frozen=True)
class CompilerRoute:
    """One registered ``(layout, artifact type)`` to compiler binding.

    ``writes_artifact`` is the opt-out for a route Godot's own import already
    serves. A writing route must rebuild a file distinct from its source; a
    non-writing route must name the source itself and change nothing.
    """

    source_layout_type: str
    artifact_type: str
    compiler_id: str
    compiler_version: int
    compiler: Compiler
    writes_artifact: bool = True

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
        writes_artifact: bool = True,
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
        if type(writes_artifact) is not bool:
            raise CompilerError("writes_artifact must be a bool")
        if not writes_artifact and artifact_type not in SOURCE_IS_ARTIFACT_TYPES:
            raise CompilerError(
                f"{artifact_type} must compile a new file; only "
                f"{', '.join(SOURCE_IS_ARTIFACT_TYPES)} may be registered as a "
                "non-writing route"
            )

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
            writes_artifact=writes_artifact,
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

        paths_match = request.artifact_path == request.source_path
        if route.writes_artifact and paths_match:
            raise CompilerError(
                f"{route.compiler_id} must compile a new file; artifact_path may "
                f"not be the source image itself ({request.artifact_path})"
            )
        if not route.writes_artifact and not paths_match:
            raise CompilerError(
                f"{route.compiler_id} writes no file, so artifact_path must equal "
                f"source_path; got {request.artifact_path} instead of "
                f"{request.source_path}"
            )
        before = _fingerprint(request.artifact_file())

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

        # Re-resolve rather than reuse: the first containment check ran against a
        # path whose parent directories did not exist yet, so no symlink could be
        # followed. Anything the compiler created in between is checked now.
        artifact_file = request.artifact_file()
        after = _fingerprint(artifact_file)
        if after is None or not artifact_file.is_file():
            raise CompilerError(
                f"{route.compiler_id} returned without writing {request.artifact_path}"
            )
        if route.writes_artifact and after == before:
            raise CompilerError(
                f"{route.compiler_id} returned without rebuilding "
                f"{request.artifact_path}; the file on disk is unchanged from an "
                "earlier run"
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
