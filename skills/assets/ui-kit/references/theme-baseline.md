# Complete UI Theme Baseline

Every successful `ui-kit` run builds and binds this complete non-pixel-art
baseline. A request brief selects the visual language; it does not remove
baseline components.

## Theme tokens

- Declare base scale, readable default font/font size when a valid supplied
  font is available, text colors, disabled/placeholder/selection colors,
  outline or shadow constants, and spacing constants.
- Derive semantic surface, raised surface, primary, secondary, danger, focus,
  disabled, success/progress, and text tokens from the binding reference.

## Components and states

- `Button`: base plus `PrimaryButton`, `SecondaryButton`, and `DangerButton`
  variations; each has `normal`, `hover`, `pressed`, `disabled`, and `focus`.
- `Panel` and `PanelContainer`: base and raised panels.
- `LineEdit` and `TextEdit`: normal, focus, disabled/read-only surfaces.
- `ProgressBar`: background and fill.
- `TabBar`/`TabContainer`: selected and unselected tabs.
- `CheckBox` and `CheckButton`: normal, hover, pressed, disabled, focus,
  checked, and unchecked treatment through styles and icons.
- `HSlider`/`VSlider`: track, grabber area, and highlighted grabber area.
- `HScrollBar`/`VScrollBar`: scroll, focus, grabber, highlighted grabber.
- `OptionButton` and `PopupMenu`: interaction states, panel, separator,
  checked/unchecked, arrow/submenu treatment.
- `TooltipSurface` variation over `Panel`: a tooltip panel treatment.

## Source and runtime requirements

- Produce at least three coherent source sheets: frame/state, control/nav, and
  utility-icon. Use a real provider image for each; every source report must
  link it to the same reference attachment set.
- Produce at least 16 distinct utility icons in one or more physical atlases:
  navigation, close/back, confirm, warning, information, settings, add,
  remove, lock, checkbox/radio, arrow/submenu, and progress/status affordances.
- Use explicit named rectangles for every atlas item. Each runtime icon is an
  `AtlasTexture` with that exact rectangle and a zero margin.
- Bind the compiled `StyleBoxTexture` resources directly into the final Theme;
  do not replace them with `StyleBoxFlat` or code-only colors. State resources
  that communicate different interaction semantics must use distinct source
  rectangles.
