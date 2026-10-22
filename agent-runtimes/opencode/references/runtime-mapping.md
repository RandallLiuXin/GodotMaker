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
consume project assets such as `references/scene_<name>.png`, resolve those as
project-root files.

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
