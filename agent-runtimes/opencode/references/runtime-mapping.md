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

## Delegated Roles

OpenCode project agents are published under `.opencode/agents/*.md`.

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

## MCP, Permissions, And Hooks

- MCP: OpenCode must have a configured `godot` MCP server before stages that
  depend on Godot MCP tools. If it is missing, stop with a setup handoff.
- Permissions: unattended GodotMaker runs require OpenCode permissions that do
  not deadlock on expected file edits, shell commands, git operations, and
  Godot invocations. For OpenCode CLI runs, this normally means
  `--dangerously-skip-permissions`.
- Hooks: OpenCode does not use Claude Code's `.claude/settings.json` hook
  format. GodotMaker's deterministic hook scripts remain under
  `.godotmaker/hooks`, but OpenCode hook/plugin parity is not assumed by this
  mapping. When no runtime hook exists, stages must rely on explicit validators
  or stop at the relevant gate.

## Image And VQA Capability

OpenCode as a coding-agent runtime does not automatically provide native image
generation or native image inspection. If a project config selects `native` for
`asset_image_model` or `vqa_model`, continue only when the active OpenCode
environment has that capability and the stage contract documents how to use it.
Otherwise require an API-backed image or VQA provider.

## Unsupported Capability Rule

If a capability is unavailable and no fallback above applies, stop before making
dependent edits. Report the missing capability, the stage being blocked, and the
smallest setup or handoff needed to continue.
