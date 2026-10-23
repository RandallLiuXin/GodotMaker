# OpenCode Runtime Mapping

Use this mapping whenever GodotMaker is published for OpenCode. It maps the
shared GodotMaker surface vocabulary to OpenCode-native execution behavior.

GodotMaker shared documentation may keep surface vocabulary such as `/gm-build`,
worker, reviewer, verifier, analyst, and worktree. In OpenCode, interpret those
terms through this mapping and execute the OpenCode-native equivalent.

## Invocation Vocabulary

- `/gm-*` in shared GodotMaker prose is framework surface vocabulary. In
  OpenCode, load and run the matching project-local skill from
  `.opencode/skills/<name>/SKILL.md`.
- Do not ask the user to literally type a slash command unless the active
  OpenCode session explicitly supports that alias.
- Keep reports and user-facing stage names as GodotMaker role names; only the
  execution surface changes.

## Path Vocabulary

When a shared GodotMaker reference mentions Claude-shaped paths, apply this
mapping before filesystem access:

| Shared surface path | OpenCode runtime path |
|---|---|
| `.claude/skills` | `.opencode/skills` |
| `.claude/agents` | `.opencode/agents` |
| `.claude/templates` | `.opencode/templates` |
| `.claude/config` | `.opencode/config` |
| `.claude/godotmaker.yaml` | `.opencode/godotmaker.yaml` |

When a shared skill says to read `.claude/godotmaker.yaml` for `godot_path`,
read `.opencode/godotmaker.yaml`.

## Skill-Local References

When a loaded skill says to read `references/*.md`, treat that path as relative
to the current skill directory, not the project root. For example, inside
`gm-asset`, `references/asset-runtime-pipeline.md` resolves to
`.opencode/skills/gm-asset/references/asset-runtime-pipeline.md`.

Project artifact paths are different: if a skill asks the stage to create or
consume project assets, resolve those as project-root files.

## Operation Mapping

| Operation | Class | Invocation path |
|---|---|---|
| `invoke_stage` | `native` | Call `skill({ name: "gm-<role>" })`; OpenCode discovers it at `.opencode/skills/gm-<role>/SKILL.md`. Do not assume a slash alias. |
| `invoke_supporting_skill` | `native` | Call OpenCode `skill({ name: "<supporting-skill>" })` for the published skill. |
| `read_project_config` | `native` | Read `.opencode/godotmaker.yaml` after applying the shared path mapping. |
| `read_skill_reference` | `native` | Resolve `references/`, `scripts/`, `tools/`, and bundled docs from `.opencode/skills/<skill>/`. |
| `dispatch_worker` | `gated` | Use the OpenCode task tool with `.opencode/agents/worker.md`; gate if subagent execution is unavailable. |
| `dispatch_reviewer` | `gated` | Use the task tool with `.opencode/agents/reviewer.md`; direct review is allowed only when the stage explicitly permits it. |
| `dispatch_verifier` | `gated` | Use the task tool with `.opencode/agents/verifier.md`; only explicitly mechanical checks may fall back to the lead session. |
| `dispatch_analyst` | `gated` | Use the task tool with `.opencode/agents/analyst.md`; gate when the selected model cannot inspect the declared assets. |
| `dispatch_asset_producer` | `gated` | Use the task tool with `.opencode/agents/asset-producer.md` and the selected provider brief. |
| `dispatch_decomposer` | `gated` | Use the task tool with `.opencode/agents/decomposer.md` and explicit work packages/owned files. |
| `dispatch_gdd_auditor` | `gated` | Use the task tool with `.opencode/agents/gdd-auditor.md` and the bounded audit brief. |
| `track_plan` | `emulated` | Use `todowrite` when available; otherwise maintain a concise visible checklist in session output without editing project planning files. |
| `ask_user_question` | `native` | Use OpenCode's `question` tool; gate non-interactive execution unless the skill permits a default. |
| `classify_repair_attempt` | `emulated` | Read `references/repair-attempt-accounting.md` and apply its evidence rules after each dispatch. |
| `inspect_images` | `gated` | `native` is unsupported. For `codex`, run `codex exec --ephemeral -s read-only -C <project> -i <image>... -o <result> "<constructed VQA prompt>"`, emit the result, and append the VQA log; API selectors run the skill-local visual-qa script. |
| `generate_images` | `gated` | `native` is unsupported. Use the selected `codex` or API provider path and preserve the generated-path claim/report contract. |
| `run_shell_command` | `native` | Use OpenCode `bash`, preserving cwd, exit status, and important output. |
| `access_godot_mcp` | `gated` | Call the configured OpenCode `godot` MCP server; stop with setup guidance when absent. |
| `apply_permission_policy` | `native` | Apply OpenCode permission frontmatter plus the root hook adapter; child role boundaries remain tool-owned where configured. |
| `forward_hook_context` | `emulated` | `.opencode/plugins/godotmaker-hooks.js` forwards hook `additionalContext` with `client.session.prompt(... noReply: true ...)`. |
| `detect_worktree_state` | `native` | Inspect git branch, worktree, HEAD, and host state before delegation or finish. |
| `create_or_use_isolated_workspace` | `gated` | Use OpenCode task isolation only when project-local runtime files remain available; otherwise use an allowed safe fallback or gate. |
| `finish_branch_or_handoff` | `native` | Use normal git delivery on a safe branch/worktree or provide a host handoff when branch operations are unsafe. |

## Dot-Directory File Checks

Do not use Glob to prove that a known dot-directory state file is missing.
For exact paths such as `.godotmaker/evaluation.json`,
`.godotmaker/verify_report.json`, `.godotmaker/stage.jsonl`, or
`.opencode/godotmaker.yaml`, use direct Read when the file content is needed,
or a shell existence check when only existence matters.

## Delegated Roles

OpenCode project agents are published under `.opencode/agents/*.md`.
Published OpenCode subagents omit the `model` field so OpenCode inherits the
active parent session model.

For OpenCode, ignore `model:` fields shown in shared `Agent(...)` examples.
Do not pass per-call model fields to the OpenCode task/subagent tool. Treat
`worker_model`, `asset_producer_model`, and other role model fields as
unsupported for OpenCode subagents.

Use the OpenCode task/subagent mechanism for delegated GodotMaker roles when
available. The delegate must receive the current brief and follow the matching
role definition:

| GodotMaker role | OpenCode role file |
|---|---|
| `worker` | `.opencode/agents/worker.md` |
| `reviewer` | `.opencode/agents/reviewer.md` |
| `verifier` | `.opencode/agents/verifier.md` |
| `analyst` | `.opencode/agents/analyst.md` |
| `asset-producer` | `.opencode/agents/asset-producer.md` |
| `decomposer` | `.opencode/agents/decomposer.md` |
| `gdd-auditor` | `.opencode/agents/gdd-auditor.md` |

If OpenCode subagent execution is unavailable, use a sequential fallback only
when the current stage explicitly allows the lead session to perform that role's
work. Otherwise stop and report the missing capability before editing files.

## Enforcement Class Matrix

The class records where a gate is enforced; it does not imply hook parity with
Claude Code.

| Gate | Class | Invocation or authority |
|---|---|---|
| `worker_dispatch_prerequisites` | `native` | `.opencode/plugins/godotmaker-hooks.js` invokes `check_stage_prerequisites.py` before the OpenCode `task` tool executes. |
| `delegated_write_boundaries` | `native` | OpenCode agent `permission` frontmatter provides the write boundary; the plugin additionally applies the identity-free `memory` scope. Identity-dependent Python subagent gates remain unsupported. |
| `stage_completion` | `tool-owned` | WOR-464 owns making `tools/append_stage_event.py` the portable authority. Until that lands, `stage_reminder.py` is only a non-authoritative write-time reminder. |

## Runtime Boundaries

- Use the configured OpenCode `godot` MCP server for Godot operations. If it is
  missing, stop with a setup handoff.
- Root-stage hooks remain active through `.opencode/plugins/godotmaker-hooks.js`.
- Child-session edit boundaries are governed by `.opencode/agents/*.md`
  `permission` frontmatter, not by Claude-style `agent_id` hook payloads.
- OpenCode child sessions do not provide the `agent_id` payload required by
  GodotMaker's Python subagent read/write gates. Treat unsupported child-session
  gates as degraded instead of claiming Claude Code hook parity.

## Image And VQA Capability

OpenCode as a coding-agent runtime does not provide native image generation or
native image inspection in the GodotMaker contract. If a dependent stage sees
`native` for `asset_image_model` or `vqa_model`, stop and ask for `codex` or an
API-backed selector.

## Unsupported Capability Rule

If a capability is unavailable and no fallback above applies, stop before making
dependent edits. Report the missing capability, the stage being blocked, and the
smallest setup or handoff needed to continue.
