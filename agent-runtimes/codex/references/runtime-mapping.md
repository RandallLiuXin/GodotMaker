# Codex Runtime Mapping

Use this mapping whenever GodotMaker is published for Codex. It maps the shared
GodotMaker surface vocabulary to Codex-native execution behavior.

GodotMaker shared documentation may keep surface vocabulary such as `/gm-build`,
`Task`, `TodoWrite`, worker, reviewer, verifier, analyst, and worktree. In
Codex, interpret those terms through this mapping and execute the Codex-native
equivalent.

If `.agents/references/delegation-worktree.md` is present, use it for the detailed
delegation and worktree policy; this file remains the general capability map.

## Invocation Vocabulary

- `/gm-*` in shared GodotMaker prose is surface vocabulary from the framework.
  When Codex is the selected runtime, invoke the matching Codex skill as
  `$gm-*` instead. Example: `/gm-build` means execute `$gm-build`.
- Do not ask the user to literally type a slash command inside Codex unless the
  host runtime explicitly supports that alias.
- Keep reports and user-facing stage names as GodotMaker role names; only the
  execution surface changes.

## Shared Path Vocabulary

Shared GodotMaker references are intentionally Claude-first. Do not edit each
shared skill to become Codex-aware. When Codex reads a shared reference, apply
this path mapping:

| Shared surface path | Codex runtime path |
|---|---|
| `.claude/skills` | `.agents/skills` |
| `.claude/agents` | `.agents/agents` |
| `.claude/templates` | `.agents/templates` |
| `.claude/config` | `.agents/config` |
| `.claude/godotmaker.yaml` | `.agents/godotmaker.yaml` |

Apply this mapping before filesystem access, including configuration reads.
When a shared skill says to read `.claude/godotmaker.yaml` for `godot_path`,
read `.agents/godotmaker.yaml`.

This document is the Codex compatibility layer for shared GodotMaker docs. The
source docs should keep clear GodotMaker/Claude-first semantics unless they are
Codex-only references like this file.

## Skill-Local References

When a loaded skill says to read `references/*.md`, treat that path as relative
to the current skill directory, not the project root. For example, inside
`$gm-asset`, `references/asset-runtime-pipeline.md` resolves to
`.agents/skills/gm-asset/references/asset-runtime-pipeline.md`.

Project artifact paths are different: if a skill asks the stage to create or
consume project assets, resolve those as project-root files. When the path is a
Markdown support document mentioned by a
skill instruction, prefer skill-local resolution.

## Operation Mapping

| Operation | Class | Invocation path |
|---|---|---|
| `invoke_stage` | `native` | Invoke the matching published `$gm-*` skill; map shared `/gm-*` vocabulary before execution. |
| `invoke_supporting_skill` | `emulated` | Read `.agents/skills/<skill-name>/SKILL.md` with the filesystem read tool, follow it in the current session, and pass the caller's arguments as task context. `$<skill-name>` is a user-side entrypoint only. |
| `read_project_config` | `native` | Read `.agents/godotmaker.yaml` after applying the shared path mapping. |
| `read_skill_reference` | `native` | Resolve from `.agents/skills/<skill>/`; skill-local `references/`, `scripts/`, `tools/`, and docs stay relative to that directory. |
| `dispatch_worker` | `gated` | Use `spawn_agent(agent_type="worker", message=...)` and explicitly load `.agents/agents/worker.md`; gate if spawning or required context is unavailable. |
| `dispatch_reviewer` | `gated` | Spawn a worker-type delegate that explicitly loads `.agents/agents/reviewer.md`; direct review is allowed only when the stage says so. |
| `dispatch_verifier` | `gated` | Spawn a worker-type delegate that loads `.agents/agents/verifier.md`; only mechanical checks may fall back to the lead session. |
| `dispatch_analyst` | `gated` | Spawn a delegate that loads `.agents/agents/analyst.md` and receives only declared asset paths; gate when image access or spawning is unavailable. |
| `dispatch_asset_producer` | `gated` | Spawn a delegate that loads `.agents/agents/asset-producer.md` and the selected provider brief; gate when spawning is unavailable. |
| `dispatch_decomposer` | `gated` | Spawn delegates that load `.agents/agents/decomposer.md` with explicit work packages and owned files. |
| `dispatch_gdd_auditor` | `gated` | Spawn a delegate that loads `.agents/agents/gdd-auditor.md` and the bounded audit brief. |
| `track_plan` | `native` | Use Codex `update_plan`, keeping one active item; never substitute edits to project planning artifacts. |
| `ask_user_question` | `emulated` | Use `request_user_input` when available, otherwise ask a concise normal question; gate non-interactive runs unless the skill permits a default. |
| `classify_repair_attempt` | `emulated` | Read `references/repair-attempt-accounting.md` and each worker's `Repair Attempt Evidence`; count every dispatch in `dispatch_count`, increment `repair_attempt_count` only for an evidence-complete effective repair, and keep the business task continuable at the no-progress threshold. |
| `inspect_images` | `native` | Use active Codex image inspection for `native` and `codex`; API selectors run the visual-qa script; always write the requested VQA log. |
| `generate_images` | `native` | Use active Codex image generation for `native` and `codex`, then apply the generated-path claim and `--out-report` contract. |
| `run_shell_command` | `native` | Use Codex shell execution with the active sandbox/approval policy and capture cwd, exit status, and important output. |
| `access_godot_mcp` | `gated` | Use the registered Codex `godot` MCP server; publish must register it and dependent stages stop when it is absent. |
| `apply_permission_policy` | `native` | Apply Codex sandbox/approval policy together with `.godotmaker/hooks`; never bypass denials or role locks. |
| `forward_hook_context` | `native` | Codex hook handling consumes `hookSpecificOutput.additionalContext` from the published `.codex/hooks.json` commands. |
| `detect_worktree_state` | `native` | Inspect branch, linked-worktree, detached-HEAD, host-isolation, and sandbox state before dispatch or finish. |
| `create_or_use_isolated_workspace` | `emulated` | Prefer Codex isolation when it carries runtime files; otherwise use a safe git worktree fallback or gate. |
| `finish_branch_or_handoff` | `native` | Use normal git delivery on a safe branch; in host-managed or detached environments use the host handoff controls. |

## Enforcement Class Matrix

The class records where a gate is enforced; it does not imply hook parity with
Claude Code. Codex lifecycle hooks do not provide an equivalent write-tool or
delegation preflight interception surface.

| Gate | Class | Invocation or authority |
|---|---|---|
| `worker_dispatch_prerequisites` | `prompt-level` | The active `$gm-*` skill must check its prerequisites before `spawn_agent`; Codex has no registered pre-dispatch hook for this gate. |
| `delegated_write_boundaries` | `prompt-level` | Project-local role definitions constrain delegated writes. Codex does not forward `Write` or `Edit` events to `check_file_permissions.py`. |
| `stage_completion` | `tool-owned` | WOR-464 owns making `tools/append_stage_event.py` the portable authority. Until that lands, Codex has no authoritative completion gate. |

## Delegated Roles

Codex delegation is not the Claude Code `Agent({ subagent_type: ... })` API.
Treat that block in shared references as surface vocabulary only, not an
executable Codex call. Native Codex delegation uses official Codex tool
semantics such as `spawn_agent(agent_type="worker", message=...)`.

`agent_type="worker"` is the official Codex worker type. It does not
automatically load `.agents/agents/worker.md`, `.agents/agents/reviewer.md`, or
any other GodotMaker role definition. The `message` must explicitly tell the
delegate to read or include the Codex project-local `.agents/agents/<role>.md` role
definition, the current `$gm-*` stage instructions, and any required
`references/*.md` files. If those files cannot be provided, gate before
dispatch.

Codex must classify every delegated role before dispatch:

| GodotMaker role | Preferred Codex behavior | Fallback or gate |
|---|---|---|
| `worker` | `spawn_agent(agent_type="worker", message=...)` with a message that makes the delegate read `.agents/agents/worker.md`, the worker brief, one task, disjoint file scope, and project-local framework paths. | Gate if the worker would need to write files the lead role is forbidden to write and no subagent/isolation path exists. |
| `reviewer` | `spawn_agent(agent_type="worker", message=...)` with a message that makes the delegate read `.agents/agents/reviewer.md`, reviewer references, and the integrated diff/state. | Gate unless the current skill explicitly allows the lead session to run reviewer checks. |
| `verifier` | `spawn_agent(agent_type="worker", message=...)` with a message that makes the delegate read `.agents/agents/verifier.md`, verifier references, and completed deliverables. | Direct shell verification is allowed for mechanical checks; independent verifier judgment remains gated without delegation. |
| `analyst` | `spawn_agent(agent_type="worker", message=...)` with a message that makes the delegate read `.agents/agents/analyst.md` and user-provided asset paths. | Gate or ask the user for a manual asset summary if files cannot be inspected in the current environment. |

Do not claim parallel worker execution unless Codex actually spawned isolated
workers. If running a sequential fallback, say so in the report and preserve the
same task state transitions.

## Project Tool Status Overrides

Project docs override generic Codex skill triggers. `gdtoolkit` is currently
disabled by `docs/decisions/disable-gdtoolkit.md` / ROADMAP `R-112`; do not run
it unless that decision is reversed.

## Worktree And Detached-Head Policy

Before creating or reusing isolation, detect the current checkout:

1. Already isolated by the host runtime: use it only if project-local framework
   files and hooks are present.
2. Normal branch checkout: a git worktree fallback may be used if the stage
   requires isolation and the user/project policy allows it.
3. Linked worktree: do not delete or repurpose it unless it was created by this
   stage and clearly owned by the stage.
4. Detached HEAD or host-managed task checkout: avoid branch, commit, push, or
   PR assumptions; finish with a handoff unless the host provides a safe branch
   operation.

## MCP, Hooks, Permissions, And Sandbox

- MCP: Codex uses a configured Codex MCP server. Codex publish must register `godot-mcp` by default
  through `codex mcp` and should fail if registration cannot complete.
- Hooks: `.godotmaker/hooks` remain authoritative. If a hook denies a write,
  follow the role contract or dispatch the proper role; do not bypass hooks.
- Permissions: use the Codex host runtime's sandbox and approval settings.
  Full GodotMaker pipeline runs need host permissions equivalent to Claude
  Code's `--dangerously-skip-permissions`, because Git state, isolated
  workspaces, and Godot's default user data / log directory may be outside a
  narrow project-only sandbox. For Codex CLI this means either
  `--dangerously-bypass-approvals-and-sandbox` for direct CLI runs, or
  `sandbox_mode="danger-full-access"` when starting a remote-control host
  process. `workspace-write` plus `--add-dir` is a narrower manual mode, not the
  baseline unattended parity mode.
- Remote control: mobile clients inherit the local host process permissions. To
  run the full pipeline through Codex remote control, start the host with:

```powershell
codex.cmd remote-control -c sandbox_mode='"danger-full-access"' -c approval_policy='"never"'
```

  The mobile app cannot raise filesystem permissions after connecting.
- Shell commands: run from the project root unless the skill says otherwise.
  Preserve command output needed for debugging.

## Unsupported Capability Rule

If a capability is unavailable and no fallback above applies, stop before making
dependent edits. Report the missing capability, the stage being blocked, and the
smallest setup or handoff needed to continue.
