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

## Operation mapping

| Operation | Class | Invocation path |
|---|---|---|
| `invoke_stage` | `native` | Invoke the published stage as `/skill:gm-<role>`. |
| `invoke_supporting_skill` | `emulated` | Read `.pi/skills/<skill-name>/SKILL.md` with Pi's `read` tool, follow it in the current session, and pass the caller's arguments as task context. `/skill:<skill-name>` is a user-side entrypoint only and may be disabled. |
| `read_project_config` | `native` | Read `.pi/godotmaker.yaml`, or use `python tools/agent_runtime.py <key>` for selected-runtime lookup. |
| `read_skill_reference` | `native` | Resolve `references/`, `scripts/`, `tools/`, and bundled docs from `.pi/skills/<skill>/`. |
| `dispatch_worker` | `emulated` | Call `godotmaker_delegate` with `role: "worker"`; worktree isolation is the default. |
| `dispatch_reviewer` | `emulated` | Call `godotmaker_delegate` with `role: "reviewer"`; treat read-only behavior as prompt-level, not an OS sandbox. |
| `dispatch_verifier` | `emulated` | Call `godotmaker_delegate` with `role: "verifier"` and preserve the returned report. |
| `dispatch_analyst` | `gated` | Call `godotmaker_delegate` with `role: "analyst"`; gate when the selected Pi model cannot inspect the declared assets. |
| `dispatch_asset_producer` | `emulated` | Call `godotmaker_delegate` with `role: "asset-producer"` and the selected provider brief. |
| `dispatch_decomposer` | `emulated` | Call `godotmaker_delegate` with `role: "decomposer"` and explicit work packages/owned files. |
| `dispatch_gdd_auditor` | `emulated` | Call `godotmaker_delegate` with `role: "gdd-auditor"` and the bounded audit brief. |
| `track_plan` | `emulated` | Maintain a concise visible checklist in Pi session output; do not edit project planning artifacts as a substitute. |
| `ask_user_question` | `emulated` | Ask a concise normal Pi prompt; gate a non-interactive run unless the skill permits a default. |
| `classify_repair_attempt` | `emulated` | Read `references/repair-attempt-accounting.md` and apply its evidence rules after each delegate result. |
| `inspect_images` | `gated` | `native` is unsupported. For `codex`, run `codex exec --ephemeral -s read-only -C <project> -i <image>... -o <result> "<constructed VQA prompt>"`, emit the result, and append the VQA log; API selectors run the skill-local visual-qa script. |
| `generate_images` | `gated` | `native` is unsupported. Use the selected `codex` or API provider path and preserve the generated-path claim/report contract. |
| `run_shell_command` | `native` | Use Pi `bash`, preserving cwd, exit status, and important output. |
| `access_godot_mcp` | `emulated` | Use `godotmaker_runtime` for project info and the bounded run/debug-output/stop loop. |
| `apply_permission_policy` | `gated` | Trust the project with `pi --approve`; role restrictions are prompt-level and must fail closed when required resources are missing. |
| `forward_hook_context` | `unsupported` | Pi publishes no hook adapter. Do not claim hook context injection; rely on skill output and the extension's explicit results. |
| `detect_worktree_state` | `native` | Inspect git branch, worktree, HEAD, and project trust before delegation or finish. |
| `create_or_use_isolated_workspace` | `emulated` | `godotmaker_delegate` creates and validates a git worktree; `shared` is allowed only for one non-parallel role. |
| `finish_branch_or_handoff` | `native` | Inspect returned merge-candidate branches, merge safely, and use normal git delivery or a host handoff. |

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
