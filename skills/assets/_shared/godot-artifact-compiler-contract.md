# Godot Artifact Compiler Contract

The compiler registry maps a validated source layout to a final Godot resource
type. It writes or verifies the resource named by a Skill result; it does not
create asset registration records.

| Source layout | Final types |
|---|---|
| `single` | `Texture2D`, `StyleBoxTexture` |
| `grid_sheet` | `SpriteFrames` |
| `region_atlas` | `AtlasTexture`, `StyleBoxTexture` |
| `theme_recipe` | `Theme` |
| `tile_atlas` | `TileSet` |

The direct result-registration command validates the final type/path against
the request-owned output contract before updating `ASSETS.md`.
