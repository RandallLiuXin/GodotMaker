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
- Added `tools/seal_tag.py index`, `backfill` and `reindex` for sealing a new tag archive, retrofitting index files onto archives sealed by an older release, and rebuilding `docs/tags/README.md` from the sealed archives on disk.

## Changed

- `/gm-finalize` now archives the `memory/` subtree with `MEMORY.md`, link-checks the archived index, and refuses to overwrite an already-sealed tag archive.
- The finalize completion gate now requires a parseable `evidence/manifest.json` with `"sealed": true` and a parent index that lists the tag, instead of only checking that the archive files exist.
- `docs/tags/README.md` is now written after the seal it describes and rendered only from manifests already on disk, so an interrupted seal can never leave the index advertising an unsealed tag.
- A forced tag-archive rewrite retires the existing seal and index entry before overwriting any file, so a failed rewrite cannot leave `"sealed": true` over hashes that no longer match the archive.
- A tag archive now mirrors deletions: a `memory/` or `e2e/` subtree that no longer exists in the project is dropped from the archive instead of being carried into the next snapshot.

## Fixed

## Removed
