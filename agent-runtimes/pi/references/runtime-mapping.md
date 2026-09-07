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
  run the normal build/verify gates.

Before using `worktree` delegation, commit the published runtime resources that
the delegate must receive: `.pi/`, `.godotmaker/config.yaml` and hooks,
`tools/`, and `AGENTS.md`. The extension verifies these resources inside every
new worktree and fails closed when they are absent; it does not copy untracked
files into an isolated worker. `shared` is only for one non-parallel role and
does not provide isolation.

Pi has no per-role filesystem permission model. Reviewer and verifier prompts
prohibit mutation, but that is not a hard sandbox boundary when `bash` is
available. Treat their result as independent model judgment, not OS-enforced
read-only execution.

The same applies to the project memory notebook: no delegated role may write
root `MEMORY.md` or any file under the project-root `memory/`. The
prohibition travels in the
role definition and in the Pi runtime contract the extension appends, and a
delegate report claiming a memory write is rejected. Delegates return execution
results and failure evidence; the lead session owns project memory.

If the extension, trust, `pi` binary, `git HEAD`, or configured Godot executable
is unavailable, stop before the dependent stage and state the missing setup.
Pi's `--approve` trusts project resources only; it does not bypass an OS
sandbox or grant permissions beyond the Pi process.
Pi child processes also inherit their parent environment and may read ancestor
`AGENTS.md` files. Run delegation from a clean project environment and do not
place workspace credentials in inherited environment variables.

## Capability boundaries

- Built-in `bash`, `read`, `edit`, and `write` cover source edits and the
  existing project scripts.
- Native image generation and native VQA are unsupported for Pi. Configure
  `codex` or an API-backed image/VQA selector before an asset-dependent stage.
- Do not claim a delegated worker, reviewer, or verifier ran unless
  `godotmaker_delegate` returned its actual result. If dispatch fails, fail
  closed rather than having the lead session impersonate the isolated role.
