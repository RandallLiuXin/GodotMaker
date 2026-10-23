# Claude Code Runtime Mapping

Use this mapping when reasoning about GodotMaker on Claude Code. It records the
current Claude Code behavior so other runtime mappings can stay symmetric.

## Invocation Vocabulary

- `/gm-*` is the native Claude Code command surface for GodotMaker role skills.
- GodotMaker role names such as worker, reviewer, verifier, and analyst map to
  Claude Code subagents when the skill dispatches them.

## Operation Mapping

| Operation | Class | Invocation path |
|---|---|---|
| `invoke_stage` | `native` | Invoke the matching project-local `/gm-*` role skill. |
| `invoke_supporting_skill` | `native` | Use Claude Code's `Skill` tool with the published supporting-skill name. |
| `read_project_config` | `native` | Read `.claude/godotmaker.yaml` for `godot_path` and project settings. |
| `read_skill_reference` | `native` | Resolve from `.claude/skills/<skill>/`; `references/`, `scripts/`, `tools/`, and bundled docs are relative to that directory. |
| `dispatch_worker` | `native` | Use `Agent`/`Task` with `subagent_type: "worker"` and `references/worker-dispatch.md`. |
| `dispatch_reviewer` | `native` | Use `Agent`/`Task` with `subagent_type: "reviewer"` and the reviewer report contract. |
| `dispatch_verifier` | `native` | Use `Agent`/`Task` with `subagent_type: "verifier"` and the verifier report contract. |
| `dispatch_analyst` | `native` | Use `Agent`/`Task` with `subagent_type: "analyst"` and `references/analyst-dispatch.md`. |
| `dispatch_asset_producer` | `native` | Use `Agent`/`Task` with `subagent_type: "asset-producer"` and one production-unit brief. |
| `dispatch_decomposer` | `native` | Use `Agent`/`Task` with `subagent_type: "decomposer"` and explicit owned files. |
| `dispatch_gdd_auditor` | `native` | Use `Agent`/`Task` with `subagent_type: "gdd-auditor"` and the bounded audit brief. |
| `track_plan` | `native` | Use `TodoWrite`; do not substitute edits to `PLAN.md` or `GAP.md`. |
| `ask_user_question` | `native` | Use `AskUserQuestion`; gate a non-interactive run when the skill does not permit a default. |
| `classify_repair_attempt` | `emulated` | Read `references/repair-attempt-accounting.md` and apply its evidence rules after each worker dispatch. |
| `inspect_images` | `gated` | For `native`, use Claude's image-reading path; for `codex`, run Codex image inspection; for API selectors, run the visual-qa script. Gate when the selected path is unavailable. |
| `generate_images` | `gated` | Use the active Claude path for `native`, `codex exec` for `codex`, or the selected API provider, then follow the generated-path claim protocol. |
| `run_shell_command` | `native` | Use Claude Code shell execution and preserve cwd, exit status, and important output. |
| `access_godot_mcp` | `gated` | Call the registered Claude `godot` MCP server; stop with setup guidance when it is absent. |
| `apply_permission_policy` | `native` | Apply published Claude settings and `.godotmaker/hooks`; never bypass a hook or role lock. |
| `forward_hook_context` | `native` | Claude Code consumes hook `hookSpecificOutput.additionalContext` directly. |
| `detect_worktree_state` | `native` | Inspect git branch, worktree, and HEAD state before delegation or finish operations. |
| `create_or_use_isolated_workspace` | `native` | Use Claude Code worktree isolation with published carry-over files; do not remove externally owned worktrees. |
| `finish_branch_or_handoff` | `native` | Finish on the current safe branch/worktree or hand off when checkout state prevents commit, push, or PR work. |

## Enforcement Class Matrix

The class records where a gate is enforced; it does not imply hook parity with
another runtime.

| Gate | Class | Invocation or authority |
|---|---|---|
| `worker_dispatch_prerequisites` | `native` | Claude Code `PreToolUse` invokes `check_stage_prerequisites.py` for both `Agent` and `Task`. |
| `delegated_write_boundaries` | `native` | Claude Code `PreToolUse` forwards `Write` and `Edit` with subagent identity to `check_file_permissions.py`. |
| `stage_completion` | `tool-owned` | WOR-464 owns making `tools/append_stage_event.py` the portable authority. Until that lands, `stage_reminder.py` is only a non-authoritative write-time reminder. |

## Gate Rule

If a required Claude Code mechanism is missing in a project-local publish, stop
and report the missing file, command, MCP server, or permission rather than
silently continuing with weaker semantics.
