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

The extension owns one role policy table. When dispatch omits `model`, it reads
the role's key from `.godotmaker/config.yaml`, falling back to `inherit`. An
explicit non-empty `model` on the dispatch request takes precedence. The
cross-runtime Claude aliases `haiku`, `sonnet`, and `opus`, plus the explicit
value `inherit`, suppress `--model` so the child inherits Pi's active provider
and model. Use Pi's full provider/model selector to choose a different model;
every such resolved value is passed as `--model <resolved-model>` to the Pi
subprocess.

| GodotMaker role | Model policy key | Pi delegation and isolation |
|---|---|---|
| `worker` | `worker_model` | Writable implementation role; separate git worktree by default. |
| `reviewer` | `reviewer_model` | Read-only by prompt contract; separate git worktree by default. |
| `verifier` | `verifier_model` | Read-only by prompt contract; separate git worktree by default. |
| `analyst` | `analyst_model` | May write only `assets/manifest.json`; separate git worktree by default. |
| `asset-producer` | `asset_producer_model` | Writes one scoped asset production unit; separate git worktree by default. |
| `decomposer` | `decomposer_model` | Writes only its decomposition package; separate git worktree by default. |
| `gdd-auditor` | `auditor_model` | Read-only by prompt contract; separate git worktree by default. |

Use `shared` only for one explicitly serial request whose role contract permits
the lead checkout. Parallel requests must all use worktree isolation.

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

If the extension, trust, `pi` binary, `git HEAD`, or configured Godot executable
is unavailable, stop before the dependent stage and state the missing setup.
Pi's `--approve` trusts project resources only; it does not bypass an OS
sandbox or grant permissions beyond the Pi process.
Pi child processes also inherit their parent environment and may read ancestor
`AGENTS.md` files. Run delegation from a clean project environment and do not
place workspace credentials in inherited environment variables.

## Enforcement Class Matrix

The class records where a gate is enforced; it does not imply hook parity with
Claude Code. Pi does not expose equivalent write-tool or delegation preflight
hook forwarding.

| Gate | Class | Invocation or authority |
|---|---|---|
| `worker_dispatch_prerequisites` | `prompt-level` | The active `/skill:gm-*` instructions must check prerequisites before `godotmaker_delegate`; the Pi extension has no pre-dispatch hook for this gate. |
| `delegated_write_boundaries` | `prompt-level` | Role definitions and delegate briefs constrain writes. Pi has no per-role filesystem permission model or write-time hook. |
| `stage_completion` | `tool-owned` | WOR-464 owns making `tools/append_stage_event.py` the portable authority. Until that lands, Pi has no authoritative completion gate. |

## Capability boundaries

- Built-in `bash`, `read`, `edit`, and `write` cover source edits and the
  existing project scripts.
- Native image generation and native VQA are unsupported for Pi. Configure
  `codex` or an API-backed image/VQA selector before an asset-dependent stage.
- Do not claim a delegated worker, reviewer, or verifier ran unless
  `godotmaker_delegate` returned its actual result. If dispatch fails, fail
  closed rather than having the lead session impersonate the isolated role.
