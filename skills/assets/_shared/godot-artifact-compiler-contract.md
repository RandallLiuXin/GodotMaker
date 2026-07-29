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

- **A writing route must produce a sibling staging artifact.** The registry
  passes the compiler a unique path beside the stable artifact, such as
  `panel.staging-<uuid>.tres` for `panel.tres` or
  `tileset.staging-<uuid>.res` for `tileset.res`. The final extension remains
  intact so Godot's `ResourceSaver` recognizes the resource format. After the
  compiler returns a valid file, the registry atomically commits that staging
  artifact with `Path.replace()`. A no-op compiler therefore cannot pass off
  the previous run's bytes, while compiler, validation, and commit failures
  preserve the previous stable artifact. This does not rely on filesystem
  timestamp precision, so a same-byte deterministic rebuild remains valid.
  Before a new writing compile starts, the registry removes only interrupted
  staging siblings for that exact stable filename and extension. This narrow
  recovery is not a production-family orphan scan or a directory transaction.
- **A writing route must not name its source.** `artifact_path` may not equal
  `source_path` or resolve to the same file, so a compiler cannot publish its
  own source image (including through a hard link or case alias) as the
  resource a worker was promised. A file-existence check alone cannot catch
  this: the source file satisfies it.

`writes_artifact=False` is the explicit opt-out, allowed only for the artifact
types in `SOURCE_IS_ARTIFACT_TYPES` — the ones Godot's default import already
produces from the source file itself. Such a route must name its source, and
the registry rejects it if its compiler changes that source.

## Interface

```python
Compiler = Callable[[CompileRequest], Mapping[str, Any]]
```

A writing compiler receives a sibling staging `request.artifact_path`, writes
its artifact there, and returns receipt details. The registry commits that
artifact to the stable request path only after validation succeeds. A
non-writing route receives the original request, writes no artifact, and has
no staging or commit step. The compiler does not build the worker-facing
artifact object; the registry does. That asymmetry is the mechanism behind the
worker-snapshot boundary below.

`CompileRequest` carries `production_family`, `asset_id`, `source_layout_type`,
`source_path`, `artifact_type`, `artifact_path`, `project_root`, and a
family-specific `spec` mapping whose inner shape each concrete compiler owns.

`CompileResult` is `godot_artifact` plus `receipt`.

Both mapping fields — `CompileRequest.spec` and `CompileReceipt.details` — are
deep-copied at construction. They sit on frozen dataclasses that a caller, a
compiler, and a stored receipt all hold at once, so a shared reference would
make the freeze decorative and let a compiler edit what a finished receipt says
it produced. The copies deliberately remain ordinary mappings so standard
dataclass, copy, and pickle operations stay usable.

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
- a writing route's `artifact_path` equals or resolves to its `source_path`, a
  non-writing route's does not, or a non-writing compiler modifies its source;
- the compiler raises — its own `CompilerError` propagates unchanged, any other
  exception is wrapped with the compiler id so nothing escapes as a traceback;
- the compiler returns something other than a mapping;
- the compiler returns without writing its staging artifact for this run;
- the staging artifact cannot be atomically committed to the stable path.

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

Receipts are returned to the caller only after the stable artifact commit
succeeds (or, for a non-writing route, after its source-preservation checks
succeed). This layer does not define a receipt storage location; nothing
worker-facing may depend on one. A failed commit leaves no issued receipt.

## Texture2D

`single -> Texture2D` is served by `asset_compiler/texture2d.py`, registered
with `writes_artifact=False`: Godot's default import already turns the image
into a `Texture2D`, so the artifact path must equal the source path. The route
exists so the pair is a registered, validated, receipted outcome rather than an
unregistered combination.

v1 introduces no general texture-import profile system. Import settings stay
Godot's defaults; per-texture mipmap, repeat, compression, and filtering choices
remain worker decisions.

## AtlasTexture

`region_atlas -> AtlasTexture` is served by
`asset_compiler/atlas_texture.py`. Its `spec` has exactly two fields:
`metadata_path` (the fixed-slot metadata JSON beside the physical atlas PNG)
and `logical_asset_id` (the declared region name). The logical id must be a safe
single path segment and match the output `.tres` filename. The compiler requires the
metadata's `atlas_path` to exactly match `source_path`, finds exactly that
declared region, rejects malformed, duplicate, missing, or out-of-bounds
regions, and writes an independent `.tres` for every requested logical asset.

It serializes the declared `Rect2` unchanged and always sets
`AtlasTexture.margin` to `Rect2(0, 0, 0, 0)`. It does not pack, trim, discover
regions, or introduce nine-slice behavior. L4 reloads the resource through
headless Godot and checks that `AtlasTexture.atlas.resource_path` exactly equals
the declared physical atlas path, alongside its exact region and zero margin.

## StyleBoxTexture

`single -> StyleBoxTexture` and `region_atlas -> StyleBoxTexture` are served by
`asset_compiler/stylebox_texture.py`. Both routes use the same exact `spec`:

```json
{
  "texture_region": [x, y, width, height],
  "border": [left, top, right, bottom],
  "expand_margin": [left, top, right, bottom],
  "axis_stretch": {"horizontal": "tile", "vertical": "stretch"}
}
```

`texture_region` and `border` are non-negative integer pixel values; the region
must lie inside the source PNG and the opposing borders may not exceed its
width or height. `expand_margin` contains finite non-negative numbers. Each
stretch axis is explicitly one of `tile`, `tile_fit`, or `stretch`.

The compiler assigns the source texture directly and writes exactly the
declared `StyleBoxTexture.region_rect`. It does not infer a region from pixels
or fixed-slot metadata, choose borders, alter margins, or generate Theme or
Control layout. L4 reloads the resource through headless Godot and requires its
source path, texture region, border, expand margins, and both stretch modes to
match the recipe exactly.

## Boundary

`_shared/` holds cross-skill material only. It has no `SKILL.md` and is not
independently triggerable. It ships the shared `Texture2D`, fixed-slot
`AtlasTexture`, `SpriteFrames`, and `StyleBoxTexture` routes; `Theme` and
`TileSet` remain family-specific compilers registered through
`CompilerRegistry.register()`.

`asset_compiler/theme.py` is the UI family's `theme_recipe -> Theme` compiler.
It validates the recipe's closed ClassDB type, item-property, resource, and
StyleBox-reference sets before serializing a deterministic `.tres`; callers
register it, and its `theme` L4 structure validator, into their per-run
registries.

There is no module-level default registry instance. A caller builds one with
`build_default_registry()` and every family compiler for that run registers into
that instance. A process-global would let one caller's registrations be
invisible to a second caller holding a freshly built registry, and — because
`register()` rejects a duplicate pair outright — would turn a re-imported
self-registering module into an import-time crash.

`asset_compiler/` imports `tools/asset_stable_entry.py` through a path bridge
that supports both the source checkout and the published project layout.
`tools/publish.py` deploys this shared implementation to
`.godotmaker/asset-runtime/`, adjacent to the published `tools/` directory,
without exposing `_shared` as a standalone Skill.
