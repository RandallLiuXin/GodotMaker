# Changelog

---

## Released versions

The canonical, full-detail changelog is maintained in the repository root:

[CHANGELOG.md on GitHub](https://github.com/RandallLiuXin/GodotMaker/blob/main/CHANGELOG.md)

### 0.1.0 — 2026-04-26 (initial public release)

- 9-role pipeline delivered as individual `/gm-*` slash commands (`/gm-scaffold`, `/gm-gdd`, `/gm-asset`, `/gm-build`, `/gm-verify`, `/gm-evaluate`, `/gm-fixgap`, `/gm-accept`, `/gm-finalize`), replacing the earlier monolithic orchestrator approach.
- Worker / verifier / reviewer / analyst sub-agent dispatch with format-validated reports and anti-deadloop protection.
- 9 role skills + 12 supporting skills + 8 reviewer skills (physics, animation, ui, tilemap, navigation, shader, audio, particles).
- 8 hook scripts enforcing per-role file-write permissions, stage prerequisite gating, sub-agent report validation, and completion diligence checks.
- `tools/publish.py` deploys the framework into a target Godot project with semantic version tracking and upgrade prompts.
- Static checks: `check_project.py` for project completeness, `check_classname.py` for Godot built-in name conflicts.
- Asset pipeline: `asset_source_generate.py` (Gemini / OpenAI / xAI source generation) and sprite-processing helpers.
- Wiki documentation across 8 sections.
- 193+ unit tests for hooks and tools.

---

## What's coming next

Pending changes for the next release are tracked in [`../../update/next.md`](../../update/next.md).

Contributors: every pull request must add an entry to `next.md` under the appropriate category (`Added`, `Changed`, `Fixed`, `Removed`) before merging. At release time, `next.md` is archived as `docs/update/vX.Y.Z.md` and a blank copy replaces it.

---

## Migration scripts

When an upgrade requires rewriting files in an existing target project, a migration script handles the transition automatically. Migration scripts live under `migrations/` in the GodotMaker repository, named by UTC timestamp (e.g., `migrations/20260429100000_fix_state_path.py`). Each target project tracks which scripts it has applied in `.godotmaker/applied_migrations.json`; on every upgrade `tools/publish.py` applies the diff in chronological order. The mechanism is decoupled from the product's MAJOR.MINOR.PATCH version — any non-MAJOR upgrade may carry migrations. (MAJOR upgrades skip migrations and use `--force` clean re-init, then re-baseline.)

You can also run migrations manually for testing:

```bash
python tools/migrate.py /path/to/my-game
```

For the full upgrade and downgrade policy, including what happens at MAJOR version boundaries, see [`../../versioning.md`](../../versioning.md).
