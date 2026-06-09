# Versioning & Upgrades

How GodotMaker tracks versions and handles upgrades between releases.

## Version Scheme

GodotMaker uses [Semantic Versioning](https://semver.org/): `MAJOR.MINOR.PATCH`

| Level | Meaning | Example | Upgrade behavior |
|-------|---------|---------|------------------|
| **PATCH** | Backward-compatible bug fixes, no new behavior | `0.3.0 → 0.3.1` | Auto-proceed; applies any pending migrations |
| **MINOR** | Backward-compatible new features or behavior changes | `0.3.0 → 0.4.0` | Show changelog, require confirmation; applies any pending migrations |
| **MAJOR** | Breaking changes (incompatible) | `0.x → 1.x` | Strong warning; requires `--force` clean re-init (skips migrations, baselines instead) |

### What "backward-compatible" means in this project

GodotMaker is a framework that deploys files into a target project, not a library
with a public API. So the compatibility contract has two specific clauses:

- **User-saved files keep their format.** `CLAUDE.md`, `.claude/godotmaker.yaml`,
  `.godotmaker/config.yaml`, and the user's own game code/scenes/assets are never
  rewritten silently. Their schema/format from the previous version must still parse.
- **Runtime state stays readable.** State files written by old hooks/skills
  (`state.json` fields, `metrics*.jsonl` schema, `stage.jsonl`, `current_role`,
  etc.) must still be readable by the new version — either directly, or via a
  migration script that rewrites them on upgrade.

Framework-managed files (skills, hooks, agents, templates, tools) are overwritten
on every publish, so changes to *those* never count as "breaking" — they are
simply re-deployed.

### Choosing a bump level

A short decision tree for contributors:

1. Old projects work after re-publish, no user-saved file or runtime state
   touched (or the change is a pure bug fix) → **PATCH**.
2. New skill / hook / behavior added; old projects' user-saved files and
   runtime state still parse and work → **MINOR**.
3. Some user-saved file format or runtime state field changed in a way the
   previous version's data cannot satisfy → **MAJOR**.

**Migrations are independent of the bump level.** A migration is a tool for
fixing or rewriting something in an existing target project; whether you need
one is a separate question from which level to bump. The migration system
itself is timestamp-driven (`migrations/<YYYYMMDDhhmmss>_<slug>.py`) and
tracked per target in `.godotmaker/applied_migrations.json`; the product
`VERSION` is not consulted. See "Version Migrations" below.

## Where Versions Live

| File | Location | Purpose |
|------|----------|---------|
| `VERSION` | GodotMaker repo root | Source of truth for current release |
| `.godotmaker/version` | Target game project | Records which version was last published |
| `CHANGELOG.md` | GodotMaker repo root | Human-readable change log per version |
| `migrations/` | GodotMaker repo root | Version migration scripts |

## Publishing & Upgrading

### Fresh Install

```bash
python tools/publish.py /path/to/my-game
```

No version exists in the target — publish proceeds directly and stamps
the version into `.godotmaker/version`.

### Upgrade (re-publish to existing project)

```bash
python tools/publish.py /path/to/my-game
```

The publish script compares the source `VERSION` against the target's
`.godotmaker/version` and behaves according to the upgrade level:

| Level | Behavior |
|-------|----------|
| **PATCH** | Proceeds automatically. Applies pending migrations (if any). |
| **MINOR** | Shows changelog, asks confirmation. Applies pending migrations (if any). |
| **MAJOR** | Blocks incremental migration. Requires `--force` for clean re-init. |

### Version Migrations

Migrations are timestamped scripts under `migrations/`, e.g.:

```
migrations/20260429100000_fix_state_path.py
migrations/20260430153000_rename_metrics_field.py
```

Each target project records which migration IDs it has applied in
`.godotmaker/applied_migrations.json`. On every publish, `migrate.py`
discovers all scripts on disk, subtracts the ones already recorded as
applied, and runs the rest in chronological order.

The system is **decoupled from MAJOR.MINOR.PATCH**. The product version
is not consulted when picking which migrations to run — the only inputs
are "what's on disk" and "what's already applied". This means PATCH
releases can ship migrations as a first-class case (e.g., a hook bug
that left orphan files in old projects gets a fix-up migration in the
PATCH that fixes the hook).

Fresh installs and MAJOR `--force` re-inits **baseline** instead: every
current migration is marked as applied without being executed, since the
target starts at the latest format and has nothing to migrate from.

If a migration fails, the chain aborts immediately. Already-successful
scripts keep their entries in `applied_migrations.json`, so re-running
publish picks up exactly where it left off.

Migrations can also be applied standalone (without re-publishing):
```bash
python tools/migrate.py /path/to/my-game
```

To scaffold a new migration:
```bash
python tools/migrate.py --new fix-state-path
# Creates migrations/<current-utc-timestamp>_fix_state_path.py
```

Full details — naming convention, scripting rules, the legacy-target
auto-bootstrap rules (empty tracker is auto-created on first contact;
pending migrations run through the normal path) — live in
`migrations/README.md`.

### MAJOR Upgrades

MAJOR version bumps indicate breaking changes that cannot be handled
by incremental migration. `publish.py` refuses to upgrade across MAJOR
boundaries without `--force`, which performs a clean re-initialization.

Full rebuild cleans all framework-managed content:
- `.claude/skills/`, `.claude/agents/`, `.claude/config/`, `.claude/templates/`
- `.godotmaker/hooks/`, `.godotmaker/stage_schemas.json`
- `.godotmaker/state.json`, `.godotmaker/metrics*.jsonl`
- `.godotmaker/applied_migrations.json` (re-baselined after re-deploy)
- `tools/`
- `.claude/settings.json` (force-overwritten)

Preserved (user configuration):
- `CLAUDE.md`, `.claude/godotmaker.yaml`, `.godotmaker/config.yaml`

After re-deploy, `publish.py` calls `baseline_applied()` to mark every
current migration as applied without running it — same as a fresh install.
The migration timestamp series itself is monotonic and global; old
scripts stay on disk as historical record.

### Downgrade

Downgrading (e.g., `0.4.0 → 0.3.0`) is blocked by default. Use `--force` to override:

```bash
python tools/publish.py --force /path/to/my-game
```

A forced downgrade still calls `run_migrations()` for routing consistency,
but in practice the call is a no-op: `applied_migrations.json` already
records every migration applied at the higher version, and the older
release ships with a subset of those scripts on disk, so `pending = disk
- applied` is empty. Migrations are not "rolled back" — that would
require explicit down-migration scripts, which this system does not
ship. If you need to roll back a schema change, restore the target
project from a VCS snapshot.

### Re-publish Same Version

Re-publishing the same version is always allowed. This is useful for
picking up local changes during development.

## Session Version Display

When a Claude Code session starts in a published project, the
`session_start.py` hook reads `.godotmaker/version` and injects
`[GodotMaker vX.Y.Z]` into the session context. This helps the
active role skill (and the user) know which framework version is deployed.

## Workflow for Releasing a New Version

1. Make your changes in the GodotMaker repo
2. Decide the bump level using the decision tree above (PATCH / MINOR / MAJOR)
3. If your changes require rewriting something in an existing target project,
   scaffold a migration with `python tools/migrate.py --new <slug>` — see
   `migrations/README.md` for details. This applies to any bump level.
4. Update `CHANGELOG.md` — add a new `## [X.Y.Z]` section at the top
5. Update `VERSION` — change to the new version number
6. Commit and (optionally) tag:
   ```bash
   git add VERSION CHANGELOG.md migrations/
   git commit -m "release: vX.Y.Z"
   git tag vX.Y.Z
   ```
7. Publish to target projects:
   ```bash
   python tools/publish.py /path/to/my-game
   ```

## What Gets Overwritten on Upgrade

Every publish overwrites:

| Directory | Content |
|-----------|---------|
| `.claude/skills/` | All skills (flattened from core + reviewer) |
| `.claude/agents/` | Agent definitions (worker, verifier, reviewer, analyst, asset-producer) |
| `.godotmaker/hooks/` | All hook scripts |
| `.claude/config/` | Config files (settings.json only with `--force`) |
| `.claude/templates/` | Document templates |
| `tools/` | Python tools (check_project, check_env, etc.) |

These are **not** overwritten (created only on fresh install):

| File | Reason |
|------|--------|
| `CLAUDE.md` | User may have customized it |
| `.claude/settings.json` | User hook configuration (overwritten only with `--force`) |
| `.claude/godotmaker.yaml` | Host-specific paths |
| `.godotmaker/config.yaml` | Project-specific settings |

## Note on addon_versions.json

`config/addon_versions.json` tracks Godot addon versions (gecs, gdUnit4, etc.)
— this is separate from GodotMaker's own version. Addon versions are pinned
per Godot engine version and managed independently.
