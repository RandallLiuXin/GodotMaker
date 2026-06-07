# Asset Prompt Contracts

This file describes prompt shapes for `/gm-asset` visual sources. Use
`asset-runtime-pipeline.md` for provider commands and source/final path
handoff.

## Shared Rules

1. Read `STYLE.md` before writing prompts.
2. Include the Style Anchor and Prompt Suffix where the prompt shape asks for
   style.
3. Use a named solid flat `{bg_color}` background for sources that need
   extraction.
4. Keep UI sheets free of text and numbers.
5. Do not request transparent backgrounds, checkerboards, or alpha grids.
6. Generate source images at full resolution.

## Scene Reference

Use scene references as visual targets for a scene. They are written under
`references/scene_{name}.png` and are not gameplay assets.

Prompt shape:

```text
Screenshot of a {2D game}. {camera/viewpoint}. Game objects: {visible objects with position and approximate size}. Environment: {layers and playfield}. HUD: {visible UI elements}. Visual style: {STYLE.md Style Anchor + Prompt Suffix}. No text labels unless the scene explicitly needs UI text.
```

Read `visual-target.md` before writing the prompt.

## Style Reference

Use style references as source images for later derivatives.

Prompt shape:

```text
{game genre and viewpoint}. Cohesive visual target sheet showing color palette, material language, shape language, UI treatment, and representative gameplay props. No text labels.
```

Record the source as `style_reference` with `production_shape:
reference_only`.

## Character Canonical

Use a canonical character image before generating action sheets or variants.

Prompt shape:

```text
{character name}, {role and visual identity}. Neutral readable pose, clean silhouette, full body visible, centered on a solid {bg_color} background. {STYLE.md prompt suffix}. No text, no UI, no cropped body parts.
```

Record the source as `character_canonical` with `production_shape:
single_image`.

## Character Action Source

Use one source per action.

Prompt shape:

```text
{character name} performing {action}. {rows}x{cols} sprite sheet, exactly {frame_count} frames, one action only, same character identity in every frame, consistent scale, centered in each cell, solid {bg_color} background. {STYLE.md prompt suffix}. No text, no UI, no borders.
```

Record the source as `character_action_source` with `production_shape:
action_sheet`. Mark `processing_status` as `needs_curation` until final frames
or final sprite sheets exist.

## Projectile Or Impact Effect Source

Use separate sources for projectiles, impacts, pickup effects, explosions, and
spawn effects.

Prompt shape:

```text
{effect name}, {effect behavior}. {rows}x{cols} effect sprite sheet, exactly {frame_count} frames, solid {bg_color} background, centered in each cell, consistent scale, no text, no UI.
```

Use `projectile_fx_source` or `impact_fx_source` and mark the source
`needs_curation` until final frames exist.

## Compact Prop Pack

Use compact prop packs for compact similarly sized props.

Prompt shape:

```text
{prop names}. {rows}x{cols} grid, one centered prop per cell, consistent scale, solid {bg_color} background, no text, no UI, no borders. {STYLE.md prompt suffix}.
```

Record rows, columns, expected item names, and final target paths in the
manifest. Mark the source `needs_curation` until extracted prop files exist.

## UI Component Sheet

Use UI component sheets for icons, small buttons, tabs, badges, counters, and
compact HUD pieces.

Prompt shape:

```text
{component names}. Clean game UI component sheet, {rows}x{cols} grid, one isolated component per cell, consistent lighting and material style, solid {bg_color} background, no text or numbers, no composite screens. {STYLE.md UI rules}.
```

Use `ui_component_sheet` or `icon_pack`. Mark the source `needs_curation` until
each final component path exists.

## Panel Source

Use panel sources for large panels, card frames, dialogue boxes, shop slots,
and menu containers.

Prompt shape:

```text
{panel name}, isolated game UI panel, empty content area, clean edges, no text, no numbers, no icons unless requested, solid {bg_color} background. {STYLE.md UI rules}.
```

Use `panel_source`. Do not force large panels into compact grid sheets.

## Background

Use backgrounds for runtime backgrounds and parallax layers.

Prompt shape:

```text
{description in the art style}. {composition instructions}. Intended game display: {viewport or parallax behavior}. No gameplay actors, pickups, hazards, UI, or text.
```

## Runtime Sprite

Use runtime sprites only when a single final image is enough.

Prompt shape:

```text
{name}, {description}. Centered on a solid {bg_color} background. Clean silhouette. {STYLE.md prompt suffix}. No text, no UI.
```

## Texture

Use textures for repeated terrain, floors, walls, UI materials, and tileable
surfaces.

Prompt shape:

```text
{name}, {description}. Uniform lighting, seamless tileable texture, clean edges, no text, no labels.
```

## Quality Notes

### Image Resolution

Use the full generation resolution. Do not downscale generated sources.

1. `1K`: default for references, characters, sprites, UI sources, textures,
   and props.
2. `512`: quick tests where supported.
3. `2K`: backgrounds, title screens, high-detail objects, and large textures.
4. `4K`: large maps and panoramic backgrounds where supported.

### Small Sprites

Minimum generation resolution is usually much larger than in-game sprite size.
If a sprite will render small in-game:

1. Prefer 128 px or larger display sizes where possible.
2. Generate a source sheet before selecting final objects.
3. Prompt for bold simple forms, thick outlines, flat colors, and exaggerated
   proportions.

### Direction And Orientation

Generate one direction and flip in-engine when appropriate.
