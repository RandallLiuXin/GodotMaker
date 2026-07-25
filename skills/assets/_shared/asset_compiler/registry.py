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
from dataclasses import dataclass, replace
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

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


def _staging_request(request: CompileRequest) -> CompileRequest:
    """Return a request whose artifact target is a unique sibling staging file.

    A compiler may overwrite the stable artifact on a successful regeneration,
    but it must never expose a partial result at that path.  Keeping the staging
    target in the same directory makes ``Path.replace`` an atomic commit on the
    target filesystem.  The final extension stays at the end of the staging
    filename because Godot's ``ResourceSaver`` selects its format from that
    extension.  The receipt still records the stable path.
    """
    parent, name = request.artifact_path.rsplit("/", 1)
    extension = Path(name).suffix
    stem = name.removesuffix(extension) if extension else name
    staging_path = f"{parent}/{stem}.staging-{uuid4().hex}{extension}"
    return replace(request, artifact_path=staging_path)


def _content_digest(path: Path) -> bytes | None:
    """Return a content digest, or ``None`` when ``path`` cannot be read.

    Only non-writing routes use this check. They are allowed to reuse their
    source as the artifact, so existence cannot show whether their compiler
    clobbered that source. Hashing gives this narrow route class a real
    fail-closed guard without making writing compilers read large artifacts
    twice merely to detect a no-op.
    """
    digest = sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.digest()


def is_same_file(left: Path, right: Path) -> bool:
    """True when two paths name one file: a hard link, or a case alias.

    Distinct path strings are not distinct files. ``os.link`` gives a compiler a
    second name for its source image, and on a case-insensitive filesystem
    ``Hero.png`` and ``hero.png`` are already one file without any linking.

    Exported because the readiness ladder re-checks the same rule on an entry it
    did not compile itself, and a second copy of it could drift.
    """
    try:
        return left.samefile(right)
    except OSError:
        return False


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
        # Receipt values are public diagnostic data, so field equality cannot
        # prove that a caller actually ran this registry. Retain the exact
        # instances returned by ``compile`` for the lifetime of this per-run
        # registry and check identity at the validation boundary.
        self._issued_receipts: dict[int, CompileReceipt] = {}

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

    def issued_receipt(self, receipt: CompileReceipt) -> bool:
        """Return whether ``receipt`` is this registry's exact compile result.

        ``CompileReceipt`` is intentionally a public, serializable dataclass,
        so an equal value may be constructed without invoking a compiler. The
        identity registry is the non-persistent capability that distinguishes a
        compiler result from such a forgery. It is deliberately scoped to this
        registry instance and is never written into a stable entry.
        """
        return self._issued_receipts.get(id(receipt)) is receipt

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
        if route.writes_artifact:
            artifact_file = request.artifact_file()
            if is_same_file(source_file, artifact_file):
                raise CompilerError(
                    f"{route.compiler_id} may not publish source_path as "
                    f"artifact_path ({request.artifact_path})"
                )
            source_digest = None
        else:
            source_digest = _content_digest(source_file)
            if source_digest is None:
                raise CompilerError(f"source_path cannot be read: {request.source_path}")

        staging_request = _staging_request(request) if route.writes_artifact else request
        staging_file: Path | None = None
        if route.writes_artifact:
            staging_file = (
                Path(staging_request.project_root)
                / staging_request.artifact_path.removeprefix("res://")
            )
        try:
            try:
                details = route.compiler(staging_request)
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
            artifact_file = staging_request.artifact_file()
            if not artifact_file.is_file():
                raise CompilerError(
                    f"{route.compiler_id} returned without writing {request.artifact_path}"
                )
            source_file = request.source_file()
            if not source_file.is_file():
                raise CompilerError(f"source_path not found after compilation: {request.source_path}")
            if route.writes_artifact and is_same_file(source_file, artifact_file):
                raise CompilerError(
                    f"{route.compiler_id} may not publish source_path as "
                    f"artifact_path ({request.artifact_path})"
                )
            if not route.writes_artifact and _content_digest(source_file) != source_digest:
                raise CompilerError(
                    f"{route.compiler_id} writes no artifact and must not modify "
                    f"source_path ({request.source_path})"
                )
            receipt = CompileReceipt(
                compiler_id=route.compiler_id,
                compiler_version=route.compiler_version,
                production_family=request.production_family,
                asset_id=request.asset_id,
                source_layout_type=request.source_layout_type,
                source_path=request.source_path,
                artifact_type=request.artifact_type,
                artifact_path=request.artifact_path,
                details=details,
            )
            if route.writes_artifact:
                try:
                    artifact_file.replace(request.artifact_file())
                except OSError as exc:
                    raise CompilerError(
                        f"{route.compiler_id} cannot commit artifact "
                        f"{request.artifact_path}: {exc}"
                    ) from exc
            # A receipt is a capability used to promote an entry through L2.
            # Issue it only once the stable artifact is in place, so a failed
            # atomic commit cannot leave a receipt for bytes never published.
            self._issued_receipts[id(receipt)] = receipt
            result = CompileResult(
                godot_artifact=GodotArtifact(
                    type=request.artifact_type,
                    path=request.artifact_path,
                ),
                receipt=receipt,
            )
        finally:
            if staging_file is not None:
                staging_file.unlink(missing_ok=True)

        return result
