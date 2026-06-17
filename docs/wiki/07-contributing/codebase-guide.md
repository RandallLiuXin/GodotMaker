# Codebase Guide

This page gives a folder-by-folder tour of the GodotMaker repository, with enough depth to orient you before you start editing. For a shorter overview, see [Development setup](development-setup.md). For how all the pieces wire together at runtime, keep reading.

## Repository layout

```
GodotMaker/
├── hooks/                   8 hook scripts + hooks/metrics/ subsystem
├── agents/                  sub-agent definitions (worker, verifier, reviewer, analyst, asset-producer, gdd-auditor)
├── skills/
│   ├── core/                Role skills + supporting skills + _shared/
│   └── reviewer/            8 reviewer skills (gotchas.md + checklist.md each)
├── tools/                   publish.py, check_env.py, check_project.py, asset_*.py, migrate.py
├── config/                  config.yaml.default, stage_schemas.json, addon_versions.json
├── agent-runtimes/          Runner-specific references, templates, hook config, and plugin adapters
├── templates/               Document templates (GDD, PLAN, STRUCTURE, SCENES, ASSETS, GAP, MEMORY, TOC)
├── tests/                   ~320 unit tests for hooks and tools
├── docs/                    versioning.md, hooks.md, wiki/, update/, contributing/, reference/
├── shell/                   publish.sh / publish.ps1, report.sh / report.bat
├── migrations/              Per-version-jump migration scripts
├── VERSION                  Semantic version source of truth
└── CHANGELOG.md             Per-release notes
```

---

## hooks/

Eight Python scripts enforcing pipeline rules. Each script reads a JSON payload from `sys.stdin`, decides whether to allow or block the action, and writes a JSON response to stdout (or exits 0 silently for a quiet allow).

Scripts and the events they handle:

| Script | Event | Blocks? |
|--------|-------|---------|
| `session_start.py` | SessionStart | No |
| `check_file_permissions.py` | PreToolUse (Write\|Edit) | Yes |
| `stage_reminder.py` | PreToolUse (Write\|Edit) | Yes |
| `check_stage_prerequisites.py` | PreToolUse (Agent) | Yes |
| `check_asset_access.py` | PreToolUse (Read) | Yes |
| `log_subagent.py` | SubagentStart | No |
| `on_subagent_stop.py` | SubagentStop | Delegates |
| `check_worker_report.py` | Called by on_subagent_stop.py | Yes |
| `check_completion.py` | Stop | Yes |

Hook registration (which script fires on which event) is runner-specific.
Claude Code and Codex use config files under `agent-runtimes/<agent>/config/`;
OpenCode uses `agent-runtimes/opencode/plugins/godotmaker-hooks.js` as a
plugin adapter.

### hooks/metrics/

A small subsystem for recording what happened during a session. Hooks call `record_event()` to append a JSON line to `.godotmaker/metrics_current.jsonl` (current session) and `.godotmaker/metrics_total.jsonl` (lifetime). The `state.py` module manages mutable per-session counters (block counts, etc.) in `.godotmaker/state.json`. `session_start.py` resets both on every new session.

For details on writing hooks and using the metrics API, see [Writing a hook](writing-a-hook.md).

### Permission contract layers

Role permissions are expressed in three places. They overlap on purpose, but each layer has a distinct job — when you change one, check whether the others need to follow:

| Layer | What it controls | Source of truth |
|-------|------------------|-----------------|
| `config/stage_schemas.json` | Did the role finish? Which output files must exist before the next role can start. | Read by `stage_reminder.py` (validate completion) and `check_stage_prerequisites.py` (gate worker dispatch). |
| `hooks/check_file_permissions.py` | What can the role write right now? Per-role write-scope whitelist enforced on every Write/Edit tool call. | Authoritative for runtime permissions. Schemas do **not** define write scope. |
| `skills/core/gm-*/SKILL.md` "Permission" section | Human-readable mirror of the hook rule for the role's owner. | Should match the hook; if they drift, the hook wins at runtime — but a contributor reading the skill will be misled. |

A common mistake is reading `stage_schemas.json` as if it were the full write contract. It is not — it only lists output files for the completion gate. Adding a file to a role's schema does **not** grant write permission; you also have to extend the hook's allow-list.

---

## agents/

Sub-agent definitions, one Markdown file per agent. Each file has YAML front-matter (`name`, `description`, `model`) and a system-prompt body. `publish.py` deploys them to `<target>/.claude/agents/`, where Claude Code picks them up by `subagent_type`.

| Agent | Role | Dispatched by |
|-------|------|---------------|
| `worker.md` | Implements one task end-to-end (code + unit tests) | `/gm-build`, `/gm-fixgap` |
| `verifier.md` | Mechanically checks a worker's output (build, tests, file presence) | `/gm-build`, `/gm-fixgap` |
| `reviewer.md` | Reads code against `skills/reviewer/<domain>` checklists and reports issues | `/gm-build`, `/gm-fixgap` |
| `analyst.md` | Analyses user-provided assets and produces a manifest | `/gm-asset` |
| `asset-producer.md` | Produces one generated visual asset production unit | `/gm-asset` |
| `gdd-auditor.md` | Independently audits a draft GDD against a 9-category checklist and returns 5–8 follow-up questions per pass | `game-planner` (Rounds 6 + 7) |

The dispatch protocols (call format and brief templates) live in `skills/core/_shared/{worker,verifier,reviewer,analyst}-dispatch.md` or in the owning role skill. `gdd-auditor` is invoked inline from `skills/core/game-planner/SKILL.md`.

### The two-pass GDD audit

`gdd-auditor` is the only sub-agent whose dispatch protocol does **not** live in `_shared/`. It is invoked from one place (`game-planner` Rounds 6 + 7) and the dispatch only makes sense as part of that interview script. Promoting it to `_shared/` would add indirection without buying reuse.

Two passes, both fresh-context, both invoked with the same `subagent_type`:

| Pass | Round | Input | Output | Why this pass exists |
|------|-------|-------|--------|---------------------|
| 1 | Round 6 | GDD v1 + empty `Previously Asked` | 5–8 follow-up questions | Catches gaps the planner missed during the interview |
| 2 | Round 7 | GDD v2 + the **exact** Round-6 questions in `Previously Asked` | 5–8 *new* questions | Forces the auditor to look at second-tier gaps instead of repeating itself |

The `Previously Asked` field in the Round 7 brief is mandatory, not advisory. Without it the auditor has no memory of pass 1 (fresh context) and re-asks the same questions, wasting a round. `game-planner` SKILL.md marks the field with `**You MUST populate**` and `gdd-auditor.md` lists "repeating questions in `Previously Asked`" as a hard prohibition — both layers enforce the same contract.

`auditor_model` defaults to `sonnet` (in `config/config.yaml.default`); the audit task is checklist-driven and does not need opus-tier reasoning.

---

## skills/core/

Role skills and supporting skills, one directory per skill. Each directory contains at minimum a `SKILL.md` with YAML front-matter and the prompt body.

**Role skills (9):** `gm-scaffold`, `gm-gdd`, `gm-asset`, `gm-build`, `gm-verify`, `gm-evaluate`, `gm-fixgap`, `gm-accept`, `gm-finalize`. These map 1:1 to the `/gm-*` slash commands. Each role skill writes its role name to `.godotmaker/current_role` as its first action, which is what `check_file_permissions.py` reads to enforce write rules.

**Supporting skills (11):** `game-planner`, `project-scaffold`, `godot-api`, `gecs`, `input-mapper`, `headless-build`, `gdunit-driver`, `godot-e2e`, `visual-qa`, `screenshot`, `mcp-driver`. These are reference documents loaded by role skills — users do not invoke them directly.

### skills/core/_shared/

Any reference document consumed by more than one skill lives here as the single source of truth. Examples: `worker-dispatch.md`, `verifier-dispatch.md`, `reviewer-dispatch.md`, `analyst-dispatch.md`.

At publish time, `publish_shared_refs()` reads `_shared/manifest.json` and writes each source file into every listed consumer skill's `references/` folder. Deployed copies carry an `<!-- AUTO-GENERATED -->` header and are overwritten on every publish.

**Edit rules:**
- Edit only the source under `_shared/<file>.md`. Never edit the deployed copies.
- Inside a consumer `SKILL.md`, reference the doc as `references/<file>.md` (the deployed path). Do not write `_shared/<file>` — that path does not exist in a published project.
- After adding or changing a shared doc, run `python -m pytest tests/tools/test_publish_shared.py -q` to confirm the manifest and all consumer references are consistent.

The manifest schema, add/remove flows, and debugging tips are in `docs/contributing/shared-refs.md`.

---

## skills/reviewer/

Eight reviewer skills, one per domain: `physics`, `animation`, `ui`, `tilemap`, `navigation`, `shader`, `audio`, `particles`.

Each reviewer skill directory contains exactly three files:
- `SKILL.md` — the reviewer prompt
- `gotchas.md` — a catalogue of domain-specific pitfalls that LLMs reliably get wrong
- `checklist.md` — systematic checks that map back to gotcha IDs

The reviewer sub-agent (dispatched by `gm-build` and `gm-fixgap`) reads these dynamically based on which Godot classes and APIs appear in the worker's output. For details on the reviewer structure, see [Writing a skill](writing-a-skill.md).

---

## tools/

Python CLI scripts that contributors and users run directly.

| Tool | Purpose |
|------|---------|
| `publish.py` | Deploy GodotMaker into a target Godot project |
| `check_env.py` | Verify Godot, Python, API keys are set up correctly |
| `check_project.py` | Validate a generated project for missing files and broken paths |
| `asset_source_generate.py` | Generate API-backed source images from `/gm-asset` specs |
| `asset_layout_guide.py` | Create layout-only guides for fixed-grid source images |
| `asset_action_process.py` | Process character action sheets into normalized frames and metadata |
| `asset_action_manifest_entry.py` | Build frame-output manifest entries from processed action metadata |
| `asset_sheet_process.py` | Split production-shaped 2D source sheets into curation candidates |
| `asset_curation_select.py` | Finalize selected curation candidates into runtime asset paths |
| `asset_curation_manifest_entry.py` | Build runtime manifest entries from selected curation candidates |
| `migrate.py` | Apply pending migrations to a target on any non-MAJOR upgrade; also scaffolds new ones via `--new <slug>` |

### How publish.py wires everything together

When you run `python tools/publish.py <target>`:

1. Read `VERSION` from the repo root and compare against `<target>/.godotmaker/version`. Prompt or block on MINOR / MAJOR upgrades.
2. Copy skills (flat): all directories under `skills/core/` and `skills/reviewer/` to the selected agent skill directory (`<target>/.claude/skills/` for Claude Code or `<target>/.agents/skills/` for Codex). Directories whose name starts with `_` (i.e., `_shared/`) are skipped by `publish_skills()`; shared docs are deployed into consumer `references/` folders instead by `publish_shared_refs()`.
3. Copy hooks to `<target>/.godotmaker/hooks/`.
4. Copy tools to `<target>/tools/`.
5. Copy templates to the selected agent template directory.
6. Copy `config/stage_schemas.json` to `<target>/.godotmaker/stage_schemas.json`.
7. On fresh install (or `--force`): write agent-specific instructions (`CLAUDE.md` or `AGENTS.md`), prompt for `godotmaker.yaml`, and write the selected runner's hook config or plugin adapter.
8. Stamp `<target>/.godotmaker/version` with the current version.

---

## config/

| File | What it controls |
|------|-----------------|
| `stage_schemas.json` | Per-role required outputs and programmatic checks (keys are role names) |
| `addon_versions.json` | Pinned Godot addon versions per engine version |

`stage_schemas.json` is the schema that `stage_reminder.py` and `check_stage_prerequisites.py` both read. Its keys are role names (`scaffold`, `gdd`, `build`, etc.); each value has an optional `files` array (paths that must exist) and an optional `checks` array (programmatic validator names). See [Writing a skill](writing-a-skill.md) for the full schema description.

---

## templates/

Markdown document templates that `publish.py` deploys into new game projects under the selected agent template directory. The role skills fill these in during their work. Templates include: `GDD.md`, `PLAN.md`, `STRUCTURE.md`, `SCENES.md`, `ASSETS.md`, `GAP.md`, `MEMORY.md`, `TOC.md`, `game-claude.md`.

---

## tests/

The test suite, organized by what it covers.

```
tests/
├── hooks/
│   ├── helpers.py                       Shared utilities: run_hook, is_blocked, write_completed_roles, ...
│   ├── test_check_completion.py
│   ├── test_check_file_permissions.py
│   ├── test_check_stage_prerequisites.py
│   ├── test_check_worker_report.py
│   ├── test_metrics.py
│   ├── test_session_start.py
│   └── test_stage_reminder.py
├── tools/
│   ├── conftest.py
│   ├── test_addon_versions.py
│   ├── test_check_classname.py
│   ├── test_check_env.py
│   ├── test_check_project.py
│   ├── test_migrate.py
│   ├── test_publish.py
│   └── test_publish_shared.py
└── test_pipeline_e2e.py                 End-to-end pipeline smoke test
```

`pyproject.toml` adds `hooks/` to `pythonpath` so that `from metrics import ...` resolves in hook tests without installing anything. For writing new tests, see [Testing](testing.md).

---

## docs/

Human-readable documentation that lives in the repo alongside the code.

| Path | What it contains |
|------|-----------------|
| `docs/hooks.md` | Accurate per-hook reference (post-rewrite) |
| `docs/versioning.md` | Version scheme and upgrade behaviour |
| `docs/wiki/` | The user-facing and contributor wiki |
| `docs/contributing/` | Shared-refs schema, release checklist |
| `docs/update/` | `next.md` (pending changes) and archived `vX.Y.Z.md` files |
| `docs/reference/` | API and config reference stubs |

---

## shell/

Thin wrappers for the two operations that contributors run from a terminal:

- `publish.sh` / `publish.ps1` — delegates to `python tools/publish.py`
- `report.sh` / `report.bat` — runs `python -m hooks.metrics.reporter` to generate an HTML report from a JSONL metrics file

---

## migrations/

Migration scripts run by `tools/migrate.py` on any non-MAJOR upgrade. Scripts are stored directly under `migrations/`, named by UTC timestamp (`<YYYYMMDDhhmmss>_<slug>.py`), and applied in chronological order. Each target tracks which IDs it has applied in `.godotmaker/applied_migrations.json`; the system is decoupled from the product's MAJOR.MINOR.PATCH version. MAJOR upgrades skip migrations entirely and use `--force` clean re-init, after which `baseline_applied()` re-marks every current migration as applied. See [Release process](release-process.md) for the full upgrade flow.
