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

- Added Alibaba Cloud Model Studio Wan 2.7 as an API-backed `/gm-asset` image provider with regional endpoint validation, ordered reference-image editing, and sanitized provenance reports.
- Added a bilingual, agent-assisted guide for safely re-initializing a 0.x workspace on 1.0 and migrating its project-specific documents and runtime asset bindings (#184) — @RandallLiuXin.
- Added a layered index to tag archives: a parent `docs/tags/README.md`, a per-tag `README.md` and `SUMMARY.md`, the frozen `memory/` subtree, and an `evidence/manifest.json` listing every archived file with size, SHA-256 and source revision.
- Added `tools/seal_tag.py index` and `tools/seal_tag.py backfill` for sealing a new tag archive and retrofitting index files onto archives sealed by an older release.

## Changed

- `/gm-finalize` now archives the `memory/` subtree with `MEMORY.md`, link-checks the archived index, and refuses to overwrite an already-sealed tag archive.

## Fixed

## Removed
