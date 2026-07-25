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

That table is not restated in code. `CompilerRegistry` imports the frozen
`LAYOUT_ARTIFACT_TYPES` relation from `tools/asset_stable_entry.py`, so a route
the stable-entry schema would reject cannot be registered in the first place and
the two can never drift.

A `reference` source layout, and any reference-only production family, compiles
no Godot artifact at all.

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

## Fail-closed rules

`CompilerRegistry.compile()` raises `CompilerError` — the only error type this
layer surfaces — when:

- the production family, source layout, or artifact type is unknown;
- the artifact type is not compatible with the source layout;
- the source layout, or the family, is reference-only;
- a source or artifact path is not a file under
  `res://assets/generated/<production_family>/<asset_id>/`, or depends on the
  temporary `work/` workspace;
- no compiler is registered for the pair;
- the source file does not exist;
- the compiler raises — its own `CompilerError` propagates unchanged, any other
  exception is wrapped with the compiler id so nothing escapes as a traceback;
- the compiler returns something other than a mapping;
- the compiler returns without writing its artifact.

Registration itself fails closed too: an incompatible pair, a non-callable
compiler, a non-positive version, and a second compiler for an already
registered pair are all rejected.

## Receipt boundary

`godot_artifact` is exactly `{type, path}`, built by the registry from the
request. Compiler identity, version, and internal findings live in
`CompileReceipt` and never widen the worker snapshot — a compiler cannot add a
field to the artifact even by returning one, because it never constructs it.

Receipts are returned to the caller. This layer does not define a receipt
storage location; nothing worker-facing may depend on one.

## Texture2D

`single -> Texture2D` is served by `asset_compiler/texture2d.py` and writes
nothing: Godot's default import already turns the image into a `Texture2D`, so
the artifact path must equal the source path. The route exists so the pair is a
registered, validated, receipted outcome rather than an unregistered
combination.

v1 introduces no general texture-import profile system. Import settings stay
Godot's defaults plus the project-wide pixel-art baseline; per-texture mipmap,
repeat, compression, and filtering choices remain worker decisions.

## Boundary

`_shared/` holds cross-skill material only. It has no `SKILL.md` and is not
independently triggerable. The registry holds no concrete `AtlasTexture`,
`SpriteFrames`, `Theme`, `StyleBoxTexture`, or `TileSet` compiler; each lands
with its own asset skill and registers itself through
`CompilerRegistry.register()`.
