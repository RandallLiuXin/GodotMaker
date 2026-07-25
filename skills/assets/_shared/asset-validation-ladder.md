# Asset Readiness Validation Ladder (L0-L4)

The single source of truth for what `ready` means for a generated asset, which
levels prove it, and how each one fails. Implemented by `asset_validation/` next
to this document.

`ready` is not a field an asset skill may assert. It is the conclusion of five
ordered levels, and an asset that fails any of them is not worker-consumable.

## The ladder

| Level | Name | Consumes | Proves |
|---|---|---|---|
| `L0` | `contract` | the stable entry object and the project root | the entry satisfies the v1 stable-entry schema and path contract |
| `L1` | `processed_source` | source_layout.path | deterministic source processing left a real file in the stable directory |
| `L2` | `compiled_artifact` | godot_artifact and the compiler registry | a registered compiler route produced the artifact file |
| `L3` | `godot_load` | the artifact path and a headless Godot binary | Godot imports the project, ResourceLoader.load succeeds, and the type matches |
| `L4` | `structure` | the L3 probe result and the registered structure validator | the loaded resource satisfies its type-specific structural contract |

`asset_validation/contract.py` holds this table as `LEVELS` and `tests/assets/`
asserts the two agree row for row, so the document cannot go stale.

L5 (a representative consumer can bind the artifact) and L6 (visual and semantic
quality) are evaluation layers, not runtime readiness gates. They live privately
in GodotMakerApp and are not implemented here.

## Verify, do not produce

The pipeline is generate, process, compile, *then* validate, then register. The
ladder runs after production and proves each step's result is real and belongs to
this entry. It never generates a source, calls a compiler, writes a file, or
edits the entry.

It also never decides what a caller records. `LadderResult.processing_status` is
`ready` or `failed` and nothing else: the intermediate statuses (`pending`,
`source_ready`, `compiled`) describe how far production got and are written by
the step that got there.

## Ordering and short-circuit

Levels run in order and stop at the first failure. Every later level depends on
the earlier one's output — there is no artifact to load when nothing compiled,
and no structure to check when nothing loaded. Levels after the failure are
reported as `not_run`, so a caller can distinguish "did not pass" from "was
never asked".

Each level reports one `LevelResult`: its identifier, `passed` / `failed` /
`not_run`, an error string on failure only, and diagnostic details. The ladder
does not raise for a bad asset; a failure is a result, because the caller has to
record which level failed and why. `ValidationError` is the only error type the
levels themselves surface, and construction is the only thing that raises.

## Reference assets have no rung

A reference asset — a `reference` source layout, or a reference-only production
family — is never handed to a worker as a runtime game asset and compiles no
Godot artifact. It completes at `source_ready`. Asking whether it is `ready` is a
category error, so L0 rejects it rather than inventing a pass.

## L3 runs real Godot

Parsing a `.tres` in Python would prove the text is well formed and nothing else.
L3 shells out to the engine instead, in two runs:

1. `godot --headless --path <project> --import` builds `.godot/imported`. Without
   it a fresh checkout cannot load a texture at all, and that absence is a real
   readiness failure rather than a test-environment quirk.
2. `godot --headless --path <project> --script probe.gd -- --request <path>
   --report <path>` loads each resource through
   `ResourceLoader.load(path, "", CACHE_MODE_IGNORE)` and writes a JSON report.

The verdict comes from the report file, never from the exit code or the console.
Godot 4.4 headless prints editor progress-dialog errors during `--import` and
resource errors during a failed load, and exits `0` through both; the streams are
captured for diagnostics only.

Type matching uses `Object.is_class()`, so it covers the whole inheritance chain:
an imported PNG that loads as `CompressedTexture2D` matches a declared
`Texture2D`, while a `Theme` declared as `StyleBoxTexture` does not.

`GodotProbe` takes `godot_path` from its caller rather than searching. A project
already resolves it through `tools/agent_runtime.read_godot_path`, and a
validator that silently searched `PATH` could verify an asset with a different
engine build than the project uses. A missing or unusable binary is a
`GodotProbeError`, which fails L3 — never a skipped level.

## L4 is the extension point

L3 proves Godot produced *a* resource of the declared type. It cannot prove the
resource says anything useful: a `SpriteFrames` with no animations, a `Theme`
with no type overrides, and a `TileSet` with no sources all load fine and are all
unusable. What "useful" means is per type, so L4 is registered, not fixed.

A family skill registers one validator per artifact type on a
`StructureValidatorRegistry`:

```python
structures.register(
    artifact_type="SpriteFrames",
    validator_id="sprite_frames_structure",
    validator=validate_sprite_frames,
    checks=("sprite_frames",),
)
```

`checks` names the structural facts `probe.gd` must collect during L3, so one
Godot run serves both levels. The check names are a closed set in `probe.gd`
(`KNOWN_CHECKS`); an unregistered check name is reported as an error, never
silently skipped. A family adds its check branch there together with the
validator that consumes it.

A validator raises `ValidationError` when the structure is unusable and returns
the facts it checked otherwise. Those facts are diagnostics and never widen the
worker snapshot, which stays exactly `{type, path}`.

The registry fails closed on an unregistered artifact type: an artifact nobody
can check must not reach `ready` just because no one wrote the check yet. The
shared layer ships exactly one validator — `Texture2D`, matching the one compiler
it ships — which requires the loaded texture to report a positive width and
height, because a zero-sized texture imports, loads, and gives a worker an
invisible sprite with no error anywhere.

## Fail-closed rules

The ladder concludes `failed` when:

- the entry is not a valid v1 stable entry, or its paths are not clean `res://`
  files under `assets/generated/<production_family>/<asset_id>/`;
- the entry is a reference asset;
- `source_layout.path` resolves outside the stable directory, is missing, is not
  a regular file, or is empty;
- the entry declares no `godot_artifact`;
- no compiler is registered for its `(source_layout.type, godot_artifact.type)`
  pair;
- `godot_artifact.path` resolves outside the stable directory, is missing, is not
  a regular file, or is empty;
- a writing route's `godot_artifact.path` equals or resolves to the same file as
  `source_layout.path`, or a non-writing route's does not;
- a supplied compile receipt describes a different asset, layout, or artifact;
- Godot cannot be run, times out, or writes no report;
- Godot has no importable resource at the artifact path, or
  `ResourceLoader.load` returns null;
- the loaded resource is not the declared type;
- no structure validator is registered for the artifact type, or the registered
  one rejects the structure.

Path containment is re-resolved on disk at L1 and L2 rather than trusted from
L0's string check, so a symlink inside the stable directory cannot aim the ladder
at a file it was never allowed to accept.

The compile receipt is optional because re-validating an already registered asset
has none to offer. When one is supplied it must be this asset's, so a receipt
from another compile cannot stand in as evidence.

Registration fails closed too: an artifact type no source layout compiles to, a
non-callable validator, malformed `checks`, and a second validator for an already
registered type are all rejected.

## Boundary

`_shared/` holds cross-skill material only. It has no `SKILL.md` and is not
independently triggerable.

There is no module-level default ladder or structure registry. A caller builds
them per run with `build_default_ladder()` or `build_default_structures()`, so
one caller's family registrations can never be invisible to — or collide with —
another's. This mirrors `build_default_registry()` in
[`godot-artifact-compiler-contract.md`](godot-artifact-compiler-contract.md).

The ladder does not register assets, read `ASSETS.md`, touch manifests, decide
CI policy, or make reviewer judgments. Wiring it into `/gm-asset` is separate
work.

`asset_validation/` imports `tools/` and its sibling `asset_compiler` through a
path bridge resolved relative to the repository root, so it is importable from a
source checkout only. `tools/publish.py` does not deploy `skills/assets/` yet;
the bridge asserts each directory and names it in the error rather than failing
as a bare `ModuleNotFoundError`.
