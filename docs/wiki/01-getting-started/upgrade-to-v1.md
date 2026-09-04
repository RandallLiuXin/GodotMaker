# Upgrade a 0.x Workspace to 1.0

GodotMaker 1.0 is a breaking framework release. An existing 0.x workspace
cannot run its old migrations incrementally into 1.0. It can, however, stay in
the same directory: `publish.py --force` cleanly re-initializes the managed
framework layer while preserving the game and its durable project history.

The command does not understand the design intent of an existing game. It does
not convert `GDD.md`, `PLAN.md`, or `ASSETS.md`, repair Godot scenes, or decide
whether an old generated asset still satisfies the 1.0 runtime contract. Use a
local coding agent to inspect those project-specific parts before resuming the
pipeline.

## What the clean re-initialization does

Run the command from a GodotMaker `v1.0.0` checkout:

```bash
python tools/publish.py --agent <current-agent> --force "<target>"
```

`<current-agent>` must remain the workspace's existing `claude-code`, `codex`,
`opencode`, or `pi` selection unless you are deliberately performing a separate
runtime migration.

The command:

- re-deploys the selected runtime's Skills, agents, templates, hooks or adapter,
  shared asset runtime, and tools;
- clears incompatible current pipeline state and reports;
- re-baselines the 1.0 migration tracker without executing old incremental
  migrations; and
- preserves root agent instructions, the selected runner's `godotmaker.yaml`,
  `.godotmaker/config.yaml`, game code, scenes, assets, planning documents, and
  historical evaluation, gap, and asset-generation evidence.

Custom files inside managed Skills, agents, config, templates, hooks, plugins,
extensions, runtime references, asset runtime, or `tools/` are not preserved.
Some of those paths are normally ignored by Git, so a clean working tree alone
is not proof that they can be recovered.

For Claude Code, Codex, and OpenCode, publish also updates the `godot` MCP
registration through the agent CLI. That state may live outside the repository;
the target's Git history cannot restore it.

See [Versioning](../../versioning.md) for the exact managed and preserved paths,
and [Publish](../05-tools/publish.md) for command options.

## Project contracts that need review

The largest 0.8.2-to-1.0 project-document change is the asset handoff:

- `ASSETS.md` is now the only worker-facing runtime asset catalog.
- Each logical runtime output has one row with a final Godot `Runtime Type` and
  loadable `res://` `Runtime Path`.
- Character animation is produced as a `character-bundle` `SpriteFrames`
  resource. Canonical images and action sheets remain production evidence, not
  separate worker-facing runtime rows.
- Multi-output families such as `ui-kit`, `card-kit`, and
  `compact-prop-pack` register every declared runtime output atomically.
- Reference-only assets finish at `source_ready`; they must not be presented to
  workers as loadable runtime resources.
- Generated assets normally live below
  `assets/generated/<asset-family>/<asset-id>/` and must pass the corresponding
  Asset Skill validation before a row is marked `generated`.
- `generated` and `source_ready` are written through the 1.0 validated
  request/result and atomic registration chain. They must not be restored by
  hand from old paths or old evidence.

The local agent should also reconcile `GDD.md`, the current-tag `PLAN.md`,
`STRUCTURE.md`, `SCENES.md`, `STYLE.md`, `MEMORY.md`, `ROADMAP.md`, existing
Godot resource bindings, addons, and custom runtime configuration. Not every
workspace needs every change: the on-disk game is the authority.

## Copyable agent prompt

Paste the following prompt into the coding agent that already works with the
game repository. Replace the two placeholders before starting.

```text
Upgrade this existing GodotMaker workspace from 0.x to GodotMaker v1.0.0.

Inputs:
- GodotMaker v1.0.0 checkout: <absolute-framework-path>
- Target game workspace: <absolute-target-path>

Goal:
Keep the game in its current directory, cleanly re-initialize the managed
GodotMaker framework layer, then adapt project-owned documents and runtime
bindings only where the real 1.0 contracts require it.

Hard gates:
1. Start with a read-only audit. Do not modify files or run publish until you
   have shown me the audit and I explicitly approve execution.
2. Confirm the target has a valid 0.x `.godotmaker/version`. If it is missing,
   stop: that would be a fresh install, not a proven 0.x upgrade.
3. Prove that every path and external runtime registration which v1.0.0 publish
   will delete or overwrite either contains no customization, is tracked in a
   recoverable Git checkpoint, or has a verified backup and restoration
   procedure. A clean worktree or an upgrade branch is not sufficient for
   ignored, untracked, or agent-global state. Do not create commits, backups,
   or discard changes without my authorization.
4. Determine the current agent from the deployed workspace and preserve that
   choice. It must be one of `claude-code`, `codex`, `opencode`, or `pi`.
5. Confirm the framework worktree is clean and that `git rev-parse HEAD`
   equals `git rev-list -n 1 v1.0.0`. Do not publish from an arbitrary moving
   branch or a dirty release checkout.
6. Never overwrite project documents from templates wholesale. Compare and
   migrate their meaning. Never claim an asset is ready without matching files
   and validation evidence.

Phase A - read-only audit:
- Record Git status, `.godotmaker/version`, selected agent, Godot path/config,
  and any custom edits under framework-managed runtime directories.
- Enumerate the exact at-risk paths for the selected runtime: its Skills,
  agents, config, templates, plugins/extensions, and runtime references;
  `.godotmaker/hooks/`, `.godotmaker/asset-runtime/`, and `tools/`; current
  state/report files; and the hook config or adapter that publish overwrites.
  For each customization, prove the recovery source or stop.
- For Claude Code, Codex, or OpenCode, use that runtime's CLI to record the
  complete current `godot` MCP entry and an exact command that can restore it.
  Do not rely only on `.mcp.json` or `check_project.py`: the effective MCP state
  may be stored outside the repository. Note that Claude Code and Codex publish
  remove the old entry before adding the replacement, so an add failure can
  leave no registration.
- Read `GDD.md`, `PLAN.md`, `ASSETS.md`, `STRUCTURE.md`, `SCENES.md`, `STYLE.md`,
  `MEMORY.md`, and `ROADMAP.md` when present.
- Inspect `project.godot`, addons, scenes, scripts, resource paths, generated
  assets, and retained evidence under `.godotmaker/`.
- Compare the existing project documents with the v1.0.0 templates without
  changing either side.
- Pay special attention to the 1.0 asset contract:
  * `ASSETS.md` is the sole worker-facing runtime catalog.
  * One logical runtime output maps to one row.
  * Runtime rows need a final Godot Runtime Type and loadable `res://` Runtime
    Path, normally below `assets/generated/<asset-family>/<asset-id>/`.
  * Character gameplay animation should resolve through `character-bundle` to
    `SpriteFrames`; canonical references and action source sheets are evidence,
    not additional runtime rows.
  * Reference-only outputs use `source_ready` and are not runtime resources.
  * Do not retain legacy manifest/stable-entry pointers as a compatibility
    layer; identify the actual 1.0 resource that scenes and workers load.
- Present an audit table with: item, current state, required change, evidence,
  risk, and proposed action. Separate deterministic framework re-initialization
  from project-semantic migration. Then stop for my approval.

Phase B - framework re-initialization, only after approval:
- From `<absolute-framework-path>`, run:
  `python tools/publish.py --agent <current-agent> --force "<absolute-target-path>"`
- Capture the full command and result. Stop on any error; do not hide a partial
  publish or retry with a different agent. If MCP registration fails after the
  old entry was removed, restore the recorded entry before doing anything else.
- Verify `.godotmaker/version` is `1.0.0`, the selected runtime files and
  `.godotmaker/asset-runtime/` exist, current incompatible pipeline state was
  cleared, and `.godotmaker/applied_migrations.json` was re-baselined.
- Prove that game code, scenes, assets, project documents, project config, and
  retained historical evidence were preserved.

Phase C - project-semantic migration:
- Make the smallest reviewable edits supported by Phase A evidence.
- Reconcile the structure of `ASSETS.md` with the v1.0 Runtime Type / Runtime
  Path table. Preserve useful provenance, but remove obsolete worker-facing
  rows or pointers rather than adding a compatibility reader. Leave an output
  `MISSING` or `deferred` when no valid 1.0 evidence chain can prove it.
- Never hand-edit Runtime Type, Runtime Path, or Status to bypass registration.
  A `generated` or `source_ready` result requires a validated v1.0 request and
  matching result. Use `tools/asset_result_registration.py` to validate the
  declared Godot types and resources and register the entire production unit
  atomically; a multi-output family must succeed or fail as a group. If old
  evidence cannot be reconstructed into that chain, report a blocker or ask to
  re-run the relevant Asset Skill.
- Update scene/script resource bindings when they still point at superseded
  asset outputs. Do not regenerate accepted art merely to change a path when a
  validated deterministic conversion is sufficient.
- Reconcile GDD, current-tag plan, structure, scene, style, roadmap, and memory
  documents with the actual game. If regeneration through `/gm-gdd` or another
  pipeline stage would change product intent, propose it and wait for approval.
- Treat missing provider credentials or unavailable models as blockers, not as
  permission to fabricate generated assets or validation evidence.

Phase D - verification and handoff:
- Run `python tools/check_env.py` from the upgraded workspace.
- For Claude Code, Codex, or OpenCode, query the selected agent CLI directly
  and verify that its effective `godot` MCP entry uses the intended command and
  `GODOT_PATH`. A project-local file check alone is insufficient.
- From the v1.0.0 framework checkout, run
  `python tools/check_project.py "<absolute-target-path>" --all`.
- Run the project's existing unit, Godot/headless, and E2E checks that are
  available locally. Report unavailable checks separately.
- Inspect changed Godot resources and at least one real scene path that consumes
  each migrated runtime-asset family.
- Do not resume the normal pipeline beyond any Asset Skill revalidation that I
  explicitly approved for Phase C until I approve the migration report.
- Finish with: original and final versions; exact command; preserved paths;
  changed files; migrated asset rows and bindings; automated results; manual
  checks still required; blockers; and rollback instructions.
```

## Expected handoff

A successful clean re-initialization proves only that the 1.0 framework was
deployed safely. The upgrade is complete when the local agent has also shown
that project-owned contracts match the existing game and that the game still
builds and runs. Keep those two conclusions separate in the final report.
