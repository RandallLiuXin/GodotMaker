# Asset Skills

Asset Skills turn an asset request into a validated Godot runtime resource.
`/gm-asset` selects a family and the
selected family owns its request shape, source processing, output paths, and
validation. The authoritative inventory is
`tools/asset_family_registry.py`; this page mirrors that registry.

## Shipped families

| Family | Variants | Godot artifact types | Terminal status |
|---|---|---|---|
| background-map | default | Texture2D | ready |
| card-kit | default | AtlasTexture, StyleBoxTexture, Theme | ready |
| character-bundle | default | SpriteFrames | ready |
| compact-prop-pack | default | AtlasTexture | ready |
| fx-bundle | static, animated | SpriteFrames, Texture2D | ready |
| platform-strip | single, atlas | AtlasTexture, Texture2D | ready |
| scene-prop-set | default | AtlasTexture | ready |
| tileset | default | TileSet | ready |
| ui-kit | default | AtlasTexture, StyleBoxTexture, Theme | ready |

Each family returns one or more native Godot artifacts after its complete
validation path succeeds.

To inspect or verify the same inventory directly from the source of truth, run:

```bash
python tools/asset_family_registry.py --output json
python tools/asset_family_registry.py --check
```

## L0-L4 validation

Runtime assets pass the levels in order. A failure at any level prevents the
result from being registered in `ASSETS.md` or handed to a worker.

| Level | What it proves |
|---|---|
| L0 | The public request and result match the family contract. |
| L1 | The processed source exists and satisfies the family-specific image or layout rules. |
| L2 | A registered deterministic compiler produced the declared native artifact. |
| L3 | A real headless Godot process can import, load, and type-check the artifact. |
| L4 | Type-specific structure matches the declared recipe, such as SpriteFrames animations, Theme values, atlas regions, or TileSet sources and terrain data. |

Runtime output reaches `ready` only after L0-L4 pass. Provider
availability and visual quality are separate evidence: a green structural
ladder does not claim that a remote provider was available or that its art met a
particular creative direction.

## Related pages

- [Asset tools](../05-tools/asset-tools.md) documents registration, snapshots,
  and production helpers.
- [Provider setup](../06-configuration/providers/README.md) separates coding-agent
  runtimes from image and visual-QA providers.
- [Core skills](core-skills.md) explains how `/gm-asset` fits into the role
  pipeline.
