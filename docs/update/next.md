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

- v1 generated-asset stable entry and root index schema: `tools/asset_stable_entry.py` (per-asset `production_family` / `source_layout` / minimal `godot_artifact` / `processing_status` entry written to `.godotmaker/asset-generation/entries/<tag>/<asset_id>.json`) and `tools/asset_generation_index.py` (pointer-only root index). Old `runtime_artifact` schema fails closed and must be regenerated through `/gm-asset`; no migration or compatibility read is provided.

## Changed

## Fixed

## Removed
