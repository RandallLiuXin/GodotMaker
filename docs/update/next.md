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

## Fixed

- Fixed agent tool-dispatch trace capture so prompts or responses containing invalid Unicode surrogates are recorded instead of being silently dropped.
- Redirected headless Godot's log into `.godotmaker/logs/` (keeping the five most recent per check) so verify no longer fails when a sandbox cannot create Godot's default `user://logs` directory.

## Removed
