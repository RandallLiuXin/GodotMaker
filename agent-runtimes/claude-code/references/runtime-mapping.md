# Claude Code Runtime Mapping

Use this mapping when reasoning about GodotMaker on Claude Code. It records the
current Claude Code behavior so other runtime mappings can stay symmetric.

## Invocation Vocabulary

- `/gm-*` is the native Claude Code command surface for GodotMaker role skills.
- GodotMaker role names such as worker, reviewer, verifier, and analyst map to
  Claude Code subagents when the skill dispatches them.

## Capability Mapping

| Capability | Claude Code mapping |
|---|---|
| `invoke_stage` | Invoke the matching `/gm-*` role skill. Gate if the project-local skill was not published. |
| `read_project_config` | Read the published project config path, normally `.claude/godotmaker.yaml`, for `godot_path` and project settings. |
| `read_skill_reference` | Read references from `.claude/skills/<skill>/references/` and supporting skills from `.claude/skills/`. Shared refs are deployed copies; `_shared/` is not a runtime path. |
| `dispatch_worker` | Use Claude Code `Task` with the worker agent and the brief required by `references/worker-dispatch.md`. Use worktree isolation where the skill requires it. |
| `dispatch_reviewer` | Use Claude Code `Task` with the reviewer agent and the reviewer report contract. |
| `dispatch_verifier` | Use Claude Code `Task` with the verifier agent and the verifier report contract. |
| `track_plan` | Use `TodoWrite` for visible session planning, separate from editing project files such as `PLAN.md` or `GAP.md`. |
| `native_image_inspection` | Use the active Claude Code runtime image-reading path. If unavailable, gate before visual QA. |
| `native_image_generation` | Use the selected runtime-native image-generation path. Finalize each generated source image with `tools/asset_image_finalize.py` and write the generation group JSON from `gm-asset/references/asset-gen.md`. If unavailable, gate before asset generation. |
| `run_shell_command` | Use Claude Code shell execution, preserving working directory, exit status, and important output in reports. |
| `access_godot_mcp` | Use the registered Claude MCP server for Godot when available; gate if MCP is required and not configured. |
| `apply_permission_policy` | Use the published Claude settings, hooks, and permission policy. Do not bypass `.godotmaker/hooks` or role locks. |
| `detect_worktree_state` | Inspect git state before worker isolation and finish operations. |
| `create_or_use_isolated_workspace` | Use Claude Code worktree behavior and published carry-over files where configured; avoid deleting externally owned worktrees. |
| `finish_branch_or_handoff` | Finish on the current branch/worktree according to user instructions, or hand off when the checkout state prevents a safe commit, push, or PR. |

## Gate Rule

If a required Claude Code mechanism is missing in a project-local publish, stop
and report the missing file, command, MCP server, or permission rather than
silently continuing with weaker semantics.
