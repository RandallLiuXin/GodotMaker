# Pi Runtime Mapping

Use this mapping whenever GodotMaker is published for Pi 0.84.1 or later.
Pi discovers project-local resources only after the project is trusted. Start a
project session with `pi --approve` for one-off runs, or approve it
interactively before using `/skill:gm-<role>`.

## Invocation and paths

- Invoke the nine pipeline roles as `/skill:gm-scaffold`,
  `/skill:gm-gdd`, `/skill:gm-asset`, `/skill:gm-build`,
  `/skill:gm-verify`, `/skill:gm-evaluate`, `/skill:gm-fixgap`,
  `/skill:gm-accept`, and `/skill:gm-finalize`.
- Pi's project-local skill root is `.pi/skills`; do not use Codex `$gm-*` or
  Claude/OpenCode `/gm-*` command syntax.
- Translate shared Claude-shaped paths as follows:

| Shared surface path | Pi runtime path |
|---|---|
| `.claude/skills` | `.pi/skills` |
| `.claude/agents` | `.pi/agents` |
| `.claude/templates` | `.pi/templates` |
| `.claude/config` | `.pi/config` |
| `.claude/godotmaker.yaml` | `.pi/godotmaker.yaml` |

Read `godot_path` through `python tools/agent_runtime.py godot_path`; it selects
the `.pi` sidecar from `.godotmaker/config.yaml`.

## Godot and delegation

Pi has no built-in MCP or `Agent` tool. GodotMaker publishes
`.pi/extensions/godotmaker-runtime.ts`, which is the required, narrow bridge:

- `godotmaker_runtime` provides project information, bounded headless runs, and
  a managed run/debug-output/stop loop. It replaces the `godot-mcp` path; do
  not silently omit runtime debugging.
- `godotmaker_delegate` launches role-isolated `pi --mode json --approve`
  child processes from `.pi/agents/*.md`. Worker-like jobs use a separate git
  worktree by default and return a merge-candidate branch. Run at most three
  disjoint worktree jobs in parallel, inspect their branches, merge them, then
  run the normal build/verify gates. Verifier and reviewer roles remain
  read-only by their role definitions.

If the extension, trust, `pi` binary, `git HEAD`, or configured Godot executable
is unavailable, stop before the dependent stage and state the missing setup.
Pi's `--approve` trusts project resources only; it does not bypass an OS
sandbox or grant permissions beyond the Pi process.

## Capability boundaries

- Built-in `bash`, `read`, `edit`, and `write` cover source edits and the
  existing project scripts.
- Native image generation and native VQA are unsupported for Pi. Configure
  `codex` or an API-backed image/VQA selector before an asset-dependent stage.
- Do not claim a delegated worker, reviewer, or verifier ran unless
  `godotmaker_delegate` returned its actual result. If dispatch fails, fail
  closed rather than having the lead session impersonate the isolated role.
