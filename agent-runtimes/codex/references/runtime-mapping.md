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
consume project assets such as `references/scene_<name>.png`, resolve those as
project-root files. When the path is a Markdown support document mentioned by a
skill instruction, prefer skill-local resolution.

## Capability Mapping

| Capability | Codex mapping |
|---|---|
| `invoke_stage` | Native when the published project-local skill exists under the Codex skill tree and can be invoked as `$gm-*`. If a shared reference says to run `/gm-verify`, execute `$gm-verify`. Gate if the matching `$gm-*` skill is not available. |
| `read_project_config` | Read the Codex-published project config path produced by publish, normally `.agents/godotmaker.yaml`, whenever shared docs refer to `.claude/godotmaker.yaml` or `godotmaker.yaml` config. Gate if it is missing and the stage needs `godot_path` or project settings. |
| `read_skill_reference` | Read references from the published Codex skill tree, normally `.agents/skills/<skill>/references/`. A shared skill path like `references/asset-runtime-pipeline.md` is skill-local, not project-root. Shared refs are deployed copies; do not look for `_shared/` at runtime. |
| `dispatch_worker` | Use `spawn_agent(agent_type="worker", message=...)` with a message that explicitly loads the Codex project-local worker role definition and worker brief when the Codex runtime exposes subagent spawning with project-local context. If unavailable, use a sequential fallback only for work the stage contract allows the lead agent to do directly; otherwise gate before editing. |
| `dispatch_reviewer` | Use `spawn_agent(agent_type="worker", message=...)` with a message that explicitly loads the Codex project-local reviewer role definition and reviewer references when available. If unavailable, the lead session may run the review checklist only when the skill explicitly allows non-delegated review; otherwise gate and report that Codex reviewer delegation is unsupported in this environment. |
| `dispatch_verifier` | Use `spawn_agent(agent_type="worker", message=...)` with a message that explicitly loads the Codex project-local verifier role definition and verifier references when available. If unavailable, run deterministic verification commands directly only where the verifier contract is mechanical and no independent judgment is required; otherwise gate. |
| `track_plan` | Map Claude-style `TodoWrite` planning to Codex `update_plan`. Keep exactly one active item and update status as work progresses. This is separate from editing project files such as `PLAN.md` or `GAP.md`. |
| `ask_user_question` | Map Claude-style `AskUserQuestion` to Codex `request_user_input` when that tool is available in the active mode. If unavailable, ask the user a concise normal question. In non-interactive execution, choose a conservative default only when the skill permits it and record the assumption; otherwise gate before continuing. |
| `native_image_inspection` | Use the active Codex runtime image-reading path for `native` and `codex`. Write the requested VQA log entry. If unavailable, gate before visual QA. |
| `native_image_generation` | Use the active Codex image generation path for `native` and `codex`. Follow the generated-path claim protocol in `gm-asset/references/providers/codex.md` and write the authoritative `--out-report` claim result. If unavailable, gate before asset generation. |
| `run_shell_command` | Use Codex shell execution with the current sandbox and approval policy. Capture command, working directory, exit code, and important output in the final stage report. Do not imply a command passed if it was skipped or blocked. |
| `access_godot_mcp` | Use the configured Codex MCP server for Godot. Codex publish must register `godot-mcp` by default and fail if registration cannot complete, because later GodotMaker stages depend on the MCP tools. |
| `apply_permission_policy` | Use the Codex sandbox/approval model and project hooks together. Expected framework commands should run without interactive deadlock; if approval is denied or unavailable, stop and report the blocked command. Do not bypass `.godotmaker/hooks` or role locks. |
| `detect_worktree_state` | Inspect git state before delegation or finish: normal branch, linked worktree, already-isolated workspace, detached HEAD, or host-managed task checkout. Treat detached HEAD as a handoff constraint, not as a reason to create commits blindly. |
| `create_or_use_isolated_workspace` | Prefer Codex-native isolated execution only if it carries `.agents/skills`, `.agents/agents`, `.agents/templates`, `.agents/godotmaker.yaml`, `.godotmaker/hooks`, and project files. If that cannot be guaranteed, use a git worktree fallback only when safe, or gate delegation. |
| `finish_branch_or_handoff` | On a normal branch, follow the user's commit/push/PR instructions. In Codex App or detached-head environments, do not force branch operations; summarize changes and use the host application's handoff controls when required. |

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

- MCP: Codex uses a configured Codex MCP server. Project publish registers the
  required `godot` server through `codex mcp` by default and should fail if that
  registration cannot complete.
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
