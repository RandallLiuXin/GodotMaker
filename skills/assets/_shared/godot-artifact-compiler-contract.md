# Godot Artifact Compiler Contract

The single source of truth for how any deterministic Godot artifact compiler is
invoked, what it returns, how it fails, and what it is allowed to hand a worker.
Implemented by `asset_compiler/` next to this document.

This is the L2 step of the readiness ladder: L1 produces source images, L2
compiles the native Godot resource, L3-L4 verify it. A compiler never registers
an asset, reads `ASSETS.md`, or touches manifests — that stays with `/gm-asset`.

## Routing

A compiler is registered for one `(source_layout.type, godot_artifact.type)`
pair. The pair — not the layout alone — is the routing key, because the
relation is not one-to-one:

| Source layout | Compilable artifact types |
|---|---|
| `single` | `Texture2D`, `StyleBoxTexture` |
| `grid_sheet` | `SpriteFrames` |
| `region_atlas` | `AtlasTexture`, `StyleBoxTexture` |
| `theme_recipe` | `Theme` |
| `tile_atlas` | `TileSet` |

`CompilerRegistry` does not restate that relation: it imports the frozen
`LAYOUT_ARTIFACT_TYPES` from `tools/asset_stable_entry.py`, so a route the
stable-entry schema would reject cannot be registered in the first place. The
table above is the human-readable mirror, and `tests/assets/` asserts it row for
row against the imported relation so it cannot go stale.

A `reference` source layout, and any reference-only production family, compiles
no Godot artifact at all.

## The artifact must be produced by this run

Two rules make "the compiler produced the artifact" mean something, because a
generated asset overwrites a stable path in place and the artifact usually
already exists from an earlier run:

- **A writing route must rebuild.** The registry fingerprints the artifact's
  size and modification time before and after the compiler runs, and rejects an
  unchanged file. Otherwise a compiler that silently no-ops passes off the
  previous run's bytes as this run's result.
- **A writing route must not name its source.** `artifact_path` may not equal
  `source_path`, so a compiler cannot publish its own source image as the
  resource a worker was promised. A file-existence check alone cannot catch
  this: the source file satisfies it.

`writes_artifact=False` is the explicit opt-out, allowed only for the artifact
types in `SOURCE_IS_ARTIFACT_TYPES` — the ones Godot's default import already
produces from the source file itself. Such a route must name its source, and
changes nothing.

## Interface

```python
Compiler = Callable[[CompileRequest], Mapping[str, Any]]
```

A compiler writes its artifact to `request.artifact_path` and returns its
receipt details. It does not build the worker-facing artifact object; the
registry does. That asymmetry is the mechanism behind the worker-snapshot
boundary below.

`CompileRequest` carries `production_family`, `asset_id`, `source_layout_type`,
`source_path`, `artifact_type`, `artifact_path`, `project_root`, and a
family-specific `spec` mapping whose inner shape each concrete compiler owns.

`CompileResult` is `godot_artifact` plus `receipt`.

Both mapping fields — `CompileRequest.spec` and `CompileReceipt.details` — are
deep-copied behind a read-only view at construction. They sit on frozen
dataclasses that a caller, a compiler, and a stored receipt all hold at once, so
a shared reference would make the freeze decorative and let a compiler edit what
a finished receipt says it produced.

## Fail-closed rules

`CompilerRegistry.compile()` raises `CompilerError` — the only error type this
layer surfaces — when:

- the production family, source layout, or artifact type is unknown;
- the artifact type is not compatible with the source layout;
- the source layout, or the family, is reference-only;
- a source or artifact path is not a file under
  `res://assets/generated/<production_family>/<asset_id>/`, or depends on the
  temporary `work/` workspace, or resolves out of the project through a symlink;
- no compiler is registered for the pair;
- the source file does not exist;
- a writing route's `artifact_path` equals its `source_path`, or a non-writing
  route's does not;
- the compiler raises — its own `CompilerError` propagates unchanged, any other
  exception is wrapped with the compiler id so nothing escapes as a traceback;
- the compiler returns something other than a mapping;
- the compiler returns without writing its artifact, or leaves it unchanged from
  an earlier run.

Path containment is re-checked after the compiler returns, not reused from
before it ran: the first check resolved a path whose parent directories did not
exist yet, so no symlink could be followed.

Registration itself fails closed too: an incompatible pair, a non-callable
compiler, a non-positive version, a `writes_artifact=False` claim on a type that
must compile a new file, and a second compiler for an already registered pair
are all rejected.

## Receipt boundary

`godot_artifact` is exactly `{type, path}`, built by the registry from the
request. Compiler identity, version, and internal findings live in
`CompileReceipt` and never widen the worker snapshot — a compiler cannot add a
field to the artifact even by returning one, because it never constructs it.

Receipts are returned to the caller. This layer does not define a receipt
storage location; nothing worker-facing may depend on one.

## Texture2D

`single -> Texture2D` is served by `asset_compiler/texture2d.py`, registered
with `writes_artifact=False`: Godot's default import already turns the image
into a `Texture2D`, so the artifact path must equal the source path. The route
exists so the pair is a registered, validated, receipted outcome rather than an
unregistered combination.

v1 introduces no general texture-import profile system. Import settings stay
Godot's defaults plus the project-wide pixel-art baseline; per-texture mipmap,
repeat, compression, and filtering choices remain worker decisions.

## Boundary

`_shared/` holds cross-skill material only. It has no `SKILL.md` and is not
independently triggerable. The registry holds no concrete `AtlasTexture`,
`SpriteFrames`, `Theme`, `StyleBoxTexture`, or `TileSet` compiler; each lands
with its own asset skill and registers itself through
`CompilerRegistry.register()`.

There is no module-level default registry instance. A caller builds one with
`build_default_registry()` and every family compiler for that run registers into
that instance. A process-global would let one caller's registrations be
invisible to a second caller holding a freshly built registry, and — because
`register()` rejects a duplicate pair outright — would turn a re-imported
self-registering module into an import-time crash.

`asset_compiler/` imports `tools/asset_stable_entry.py` through a path bridge
resolved relative to the repository root, so it is importable from a source
checkout only. `tools/publish.py` does not deploy `skills/assets/` yet; the
bridge asserts the directory and names it in the error rather than failing as a
bare `ModuleNotFoundError`.
