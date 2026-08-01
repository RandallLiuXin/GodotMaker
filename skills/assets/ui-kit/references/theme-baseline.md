# Complete UI Theme Baseline

Every successful `ui-kit` run builds this complete baseline. The request and
reference choose its visual language; they do not remove baseline controls.

## Deterministic Theme tokens

- Color: text, muted text, text outline, base/raised/input surfaces, primary,
  secondary, danger, success, border, focus, selection, and shadow.
- Geometry: ordered small/medium/large radii, border width, content margin,
  shadow size/offset, and font size.
- Hover, pressed, and disabled variants are derived deterministically from
  semantic colors. A provider is not asked to recreate identical colored
  surfaces for each semantic button family.

## Provider surface patches

The surface atlas contains exactly eight isolated 96x96 square patches:

- Button: normal, hover, pressed, disabled.
- Panel: base and raised.
- Tab: selected and unselected; selected also supplies hovered treatment.

Each patch follows its fixed geometry profile. All contour, outline, shadow,
highlight, and ornament stays in the outer border band. The exact safe center
is continuous and undecorated so deterministic nine-slice stretching remains
valid. Runtime reuse expands these eight regions into 23 named
`StyleBoxTexture` resources:

- Base, Primary, Secondary, and Danger buttons each expose normal, hover,
  pressed, and disabled through deterministic modulation of the four source
  states.
- Base/raised panel each use their declared source patch.
- Popup panel reuses base panel; tooltip reuses the base patch with the raised
  surface tint.
- Selected/hovered tab reuse selected art; unselected uses its own patch.

Focus is a native `StyleBoxFlat` outline rather than another provider image.

## Native flat and empty styles

Use `StyleBoxFlat` or `StyleBoxEmpty` for structures Godot can render reliably:

- `LineEdit` and `TextEdit`: normal, focus, disabled/read-only.
- `ProgressBar`: background and fill.
- `HSlider`/`VSlider`: track, filled area, highlighted fill.
- `HScrollBar`/`VScrollBar`: track, normal, highlighted, pressed grabbers.
- `OptionButton`: normal, hover, pressed, disabled, focus.
- `PopupMenu`: disabled panel, hover, separator.
- `CheckBox` and `CheckButton`: undrawn backgrounds plus focus outline.

This division keeps complete native Theme coverage while avoiding generated
nine-slice art where a stable Godot primitive is sufficient.

## Controls and Theme bindings

- `Button`, `PrimaryButton`, `SecondaryButton`, and `DangerButton`: normal,
  hover, pressed, disabled, focus.
- `Panel` and `PanelContainer`: base and raised.
- `LineEdit`, `TextEdit`, `ProgressBar`, `TabBar`, `TabContainer`, `CheckBox`,
  `CheckButton`, sliders, scrollbars, `OptionButton`, and `PopupMenu`: the
  native style states described above.
- `TooltipSurface`: a real variation over `Panel` with tooltip panel art.
- Common text types include font color, outline, size, interactive state
  colors where applicable, and spacing constants.

## Icon source and runtime contract

The icon provider sheet contains exactly 24 unique source items: navigation
arrows, back, close, confirm, warning, information, settings, add, remove,
lock/unlock, checkbox, radio, status, check-button states, and slider grabber
states. Deterministic processing keeps reusable action/status art at 128x128
and normalizes Theme-bound arrows to 32x32, checks and toggles to 40x40, and
slider grabbers to 48x48. Explicit source-to-runtime mappings publish 31
stable `AtlasTexture` resources; aliases intentionally share the same source
rect.

Only Godot-defined semantic icon properties are bound inside `Theme`, including
checkbox, check-button, slider, option-button, tab arrow, popup check/radio,
and submenu slots. Other utility icons remain independent named
`AtlasTexture` runtime outputs for workers to reuse. Godot Theme does not offer
an arbitrary icon dictionary, so do not fabricate one.

For ordinary `Button` consumers, set `expand_icon` when the layout should size
the icon and use a local `icon_max_width` only when that screen needs a cap.
Keep final Control and Container sizing in the consuming UI rather than baking
screen-specific dimensions into the Theme.

Keep native horizontal and vertical slider tracks and filled areas at a
non-zero deterministic thickness. Use contrasting `input` and `primary`
colors so the rail remains visible behind the 48x48 grabber icons.
