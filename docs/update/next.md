# Next Release

> **Contributors:** Follow the canonical [release-note entry contract](https://github.com/RandallLiuXin/GodotMaker/blob/main/CONTRIBUTING.md#release-note-entries).
> When a new version is released, this file will be archived as `vX.Y.Z.md` and a fresh copy will take its place.

## How to add an entry

Append qualifying changes under the appropriate category below. The contributor
contract defines when an entry is required, its format, and allowed categories.

---

## Added

- Added a canonical agent-operation contract with executable Claude Code, Codex, OpenCode, and Pi mappings, including runtime-neutral supporting-skill and visual QA handoffs (#226) — @RandallLiuXin.

## Changed

- Aligned generated GAP provenance and archives with evaluation-run manifests (including collision-free repeated repair rounds), centralized worker, reviewer, and verifier dispatch schemas, and resolved SCENES viewport examples from the project contract (#221) — @RandallLiuXin.
- Publishing existing projects now refreshes GodotMaker-managed runtime hooks for Claude Code, Codex, OpenCode, and Pi while preserving unrelated user configuration and independent extensions (#212) — @RandallLiuXin.
- Replaced the project `STYLE.md` visual seed with a plain-text `DESIGN.md` visual contract covering visual identity, nine image-style dimensions, UI visual language, and Do / Don't lists; existing projects migrate on publish, legacy text preserved verbatim.
- `/gm-asset` now reviews every generated asset before registration and `/gm-evaluate` reviews every scene, both rule by rule against `DESIGN.md` instead of against reference-image similarity, reporting per-rule evidence, confidence, and severity, and blocking only on high-confidence violations of `Don't`, `MUST` / `MUST NOT`, or explicitly required rules.
- Asset generation now treats `DESIGN.md` as the visual specification authority and role-labeled reference images as visual conditioning: each production unit carries its applicable design sections verbatim in the request brief, and a conflicting reference is a blocker instead of a silent drop.
- Raised the enforced and documented environment baseline to Python 3.10+, Node.js 22+, and Godot 4.5+.
- Added registry-backed Asset Skill and L0-L4 documentation, provider navigation, and current Phantom Camera and TileSet/TileMap capability status.

## Fixed

- Aligned `/gm-evaluate` E2E generation with canonical `e2e/test_*.py` pytest files so generated tests are discovered by pytest and the project checker (#210) — @RandallLiuXin.

## Removed

- Removed the project `MEMORY.md` / `memory/` subsystem. Fresh publishes no longer create, read, validate, or archive it; upgrades preserve legacy files unchanged and use `STRUCTURE.md` for architecture ownership, dependencies, ordering constraints, and stable invariants.
