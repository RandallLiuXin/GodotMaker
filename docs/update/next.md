# Next Release

> **Contributors:** Every pull request MUST include an entry in this file describing the change.
> When a new version is released, this file will be archived as `vX.Y.Z.md` and a fresh copy will take its place.

## How to add an entry

Append your change under the appropriate category below. Use this format:

```
- Brief description of the change (#PR_NUMBER) — @author
```

If no category fits, add a new one following [Keep a Changelog](https://keepachangelog.com/) conventions.

---

## Added

## Changed

- Clarified README and docs landing-page boundaries for current game types, art-pipeline limits, and long-running prototype expectations.
- Clarified that README agent runtime requirements refer to CLI-based runners.
- Updated the Godot 4.5+ godot-e2e addon pin to v1.3.0.

## Fixed

- Improved multi-frame runtime asset handling so generated actors and FX are built and reviewed for animation playback and lifecycle behavior instead of static sheet or first-frame use.
- Fixed atlas asset usage so a generated button, icon, prop, or effect is built and reviewed to show its own image instead of the whole packed sheet it was cut from.
- Fixed agent tool-dispatch trace capture so prompts or responses containing invalid Unicode surrogates are recorded instead of being silently dropped.
- Redirected headless Godot's log into `.godotmaker/logs/` (keeping the five most recent per check) so verify no longer fails when a sandbox cannot create Godot's default `user://logs` directory.
- New and existing projects now disable Godot's default engine file log (existing projects are updated by an upgrade migration) so an unattended run that floods errors can no longer fill the system drive with an unbounded `user://logs/godot.log`.

## Removed
