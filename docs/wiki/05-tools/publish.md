# Publish

`publish.py` installs the GodotMaker framework into a target Godot project folder. You'll run it once to create a project, and again whenever you upgrade GodotMaker.

## Fresh install

Point `publish.py` at an empty folder (or an existing Godot project folder). Choose the coding agent you want to use for that project:

```bash
# Claude Code
python tools/publish.py /path/to/my-game
cd /path/to/my-game
claude

# Codex
python tools/publish.py --agent codex /path/to/my-game
cd /path/to/my-game
codex

# OpenCode
python tools/publish.py --agent opencode /path/to/my-game
cd /path/to/my-game
opencode
```

On Windows:

```powershell
python tools\publish.py C:\Games\my-game
```

The first time you run this, the script will ask you for the full path to your Godot executable. Enter it when prompted — you only need to do this once per project.

**What gets created for Claude Code:**

| Location | What it is |
|----------|------------|
| `.claude/skills/` | All GodotMaker slash commands (the `/gm-*` commands and supporting skills) |
| `.claude/agents/` | Definitions for worker, verifier, reviewer, analyst, and asset-producer helpers |
| `.claude/settings.json` | Tells Claude Code which hook scripts to run and when |
| `.claude/godotmaker.yaml` | Your Godot executable path (specific to this machine) |
| `.godotmaker/hooks/` | The enforcement scripts that keep the AI on track |
| `.godotmaker/config.yaml` | Per-project settings (model choice, asset generation provider, etc.) |
| `.godotmaker/version` | Records which GodotMaker version is installed here |
| `tools/` | Utility scripts (`check_env.py`, `check_project.py`, `asset_source_generate.py`, etc.) |
| `.claude/templates/` | Document templates used by `/gm-gdd` and other commands |
| `CLAUDE.md` | Per-project instructions that Claude Code reads at the start of every session |
| `assets/sprites`, `assets/audio`, `assets/fonts`, `assets/ui`, `references/` | Standard asset folders |

The script also registers the `godot-mcp` server for the selected agent (Claude
Code via `claude mcp`, Codex via `codex mcp`, OpenCode via `opencode mcp`),
initializes a git repository if one doesn't exist, and creates a `.gitignore`
with the right entries. MCP registration is required because the GodotMaker
runtime depends on the Godot MCP tools.

When published with `--agent codex`, the agent-owned files use the Codex
layout instead: skills go under `.agents/skills/`, templates/config under
`.agents/`, `godotmaker.yaml` is stored at `.agents/godotmaker.yaml`, and
`AGENTS.md` is created instead of `CLAUDE.md`. Codex hook registration is
written to `.codex/hooks.json`. Shared framework state still lives under
`.godotmaker/`. Codex approval and sandbox policy are handled by Codex at
runtime; publish does not create a `.agents/settings.json` equivalent.

When published with `--agent opencode`, the agent-owned files use the OpenCode
layout instead: skills go under `.opencode/skills/`, agents under
`.opencode/agents/`, templates/config under `.opencode/`, `godotmaker.yaml` is
stored at `.opencode/godotmaker.yaml`, and `AGENTS.md` points to the OpenCode
runtime mapping. The OpenCode hook adapter is written to
`.opencode/plugins/godotmaker-hooks.js`; it calls the shared GodotMaker hook
scripts in `.godotmaker/hooks/`.

### Codex permissions

Codex permissions are controlled by the Codex host process, not by files that
`publish.py` writes into the project. A full GodotMaker pipeline may need to
write Git state, create or use isolated workspaces, and let Godot write its
default user data / log files. For unattended runs, start Codex with full host
permissions equivalent to Claude Code's `--dangerously-skip-permissions`.

For direct CLI automation, use the Codex full-bypass mode provided by the runner
or by your own command wrapper. For remote-control sessions, permissions are set
when the local host process starts; the mobile app cannot raise them after it
connects. Start the host like this when you intend to run the full pipeline from
remote control:

```powershell
codex.cmd remote-control -c sandbox_mode='"danger-full-access"' -c approval_policy='"never"'
```

`workspace-write` plus `--add-dir` can be used for narrower manual experiments,
but it is not the baseline unattended mode because Godot's default log directory
and sibling worktrees can be outside the project root.

## Upgrading an existing project

Run the same command again inside an already-published project. GodotMaker compares its own version number against the version recorded in `.godotmaker/version` and decides what to do:

| Upgrade type | What happens |
|--------------|--------------|
| **Patch** (e.g. 0.3.0 to 0.3.1) | Proceeds automatically — backward-compatible bug fixes. Applies any pending migrations |
| **Minor** (e.g. 0.3.0 to 0.4.0) | Shows the changelog, asks you to confirm. Applies any pending migrations |
| **Major** (e.g. 0.x to 1.x) | Requires `--force` — breaking changes that need a clean re-initialization. Skips migrations and re-baselines after re-deploy |
| **Same version** | Always proceeds — useful when you've made local changes to the framework. Also applies any pending migrations you added locally without bumping `VERSION` |
| **Downgrade** | Blocked by default; requires `--force` to override. Migrations are not rolled back (no down-migrations); restore from VCS if needed |

> Migrations and bump levels are independent. Each migration is a
> timestamped script under `migrations/`; targets record what they've
> applied in `.godotmaker/applied_migrations.json`. PATCH and MINOR both
> apply any pending scripts. See [`../../versioning.md`](../../versioning.md)
> for the full policy.

For the full upgrade policy and migration script details, see [`../../versioning.md`](../../versioning.md). For what changed in each release, see the [changelog](../08-reference/changelog.md).

## Options

```bash
python tools/publish.py --force /path/to/my-game
python tools/publish.py --agent codex --force /path/to/my-game
python tools/publish.py --agent opencode --force /path/to/my-game
```

`--force` does four things at once:

1. Clears the selected agent's skill directory before re-deploying, removing any skills left over from a previous version.
2. Overwrites the selected runner's hook config or adapter (`.claude/settings.json`, `.codex/hooks.json`, or `.opencode/plugins/godotmaker-hooks.js`) even if you've already customized it.
3. Skips the confirmation prompts for minor and major upgrades.
4. Allows downgrades.

For **major** upgrades with `--force`, the clean-up is more thorough: the selected agent's `skills/`, `agents/`, `config/`, and `templates/` folders, `.godotmaker/hooks/`, `tools/`, and the runtime state files are all wiped and rebuilt from scratch.

## What is preserved on upgrade

These files are never overwritten by a normal publish (only `--force` can change the selected runner's hook config):

| File | Why it is kept |
|------|---------------|
| `CLAUDE.md` / `AGENTS.md` | You may have added project-specific instructions |
| `.claude/settings.json` / `.codex/hooks.json` / `.opencode/plugins/godotmaker-hooks.js` | You may have adjusted hook behavior |
| `.claude/godotmaker.yaml` / `.agents/godotmaker.yaml` / `.opencode/godotmaker.yaml` | Contains your machine-specific Godot path |
| `.godotmaker/config.yaml` | Contains your project-specific preferences |

Your game code, scenes, assets, and planning documents (`GDD.md`, `PLAN.md`, etc.) are not touched by publish — it only manages the framework layer.
