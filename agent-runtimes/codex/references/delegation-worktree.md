# Codex Delegation And Worktree Policy

This reference defines how GodotMaker delegation vocabulary maps to Codex when
the selected runtime is Codex. Shared docs may still say "worker", "reviewer",
"verifier", "analyst", "Task", or "worktree"; Codex must interpret those terms
through this policy before starting the stage.

Shared docs may also name Claude-first paths and invocations. In Codex, resolve
them through the project-local Codex tree:

| Shared surface | Codex runtime |
|---|---|
| `.claude/skills` | `.agents/skills` |
| `.claude/agents` | `.agents/agents` |
| `.claude/templates` | `.agents/templates` |
| `/gm-*` | `$gm-*` |

## Delegated Role Support

Shared dispatch references may show Claude Code `Agent({ subagent_type: ... })`
blocks. In Codex, those blocks are surface semantics, not executable API calls.
Native Codex delegation uses the official Codex worker API:
`spawn_agent(agent_type="worker", message=...)`.

`agent_type="worker"` is the official Codex worker type. It does not select or
autoload GodotMaker role files from `.agents/agents/`. Every Codex delegate
message must explicitly include or instruct the delegate to read the
Codex project-local `.agents/agents/<role>.md` role definition, the current `$gm-*`
stage instructions, and the relevant `references/*.md` files. If that runtime
context cannot be supplied, use the emulated path below only when allowed, or
fail with an unsupported-with-gate report.

| Role | Codex support | Required behavior |
|---|---|---|
| worker | native when `spawn_agent(agent_type="worker", message=...)` can launch an official Codex worker with a message that loads `.agents/agents/worker.md` and project context; emulated for one bounded task by executing the worker brief sequentially in the main Codex session; unsupported-with-gate for parallel worker batches when neither runtime-native isolation nor a safe git fallback is available. | Implement only the deliverables in the worker brief, run the required checks, and report using the worker format. Workers must not spawn sub-workers. |
| reviewer | native when `spawn_agent(agent_type="worker", message=...)` can launch an official Codex worker with a message that loads `.agents/agents/reviewer.md`; emulated by running the reviewer checklist sequentially in the main Codex session against the integrated state. | Read-only review only. If reviewer skills or checklists are unreachable, fail before review starts. |
| verifier | native when `spawn_agent(agent_type="worker", message=...)` can launch an official Codex worker with a message that loads `.agents/agents/verifier.md`; emulated by running every verifier command sequentially in the main Codex session. | Read-only verification only. If sandbox or permissions prevent required commands, report an unsupported-with-gate before claiming PASS. |
| analyst | native when `spawn_agent(agent_type="worker", message=...)` can launch an official Codex worker with a message that loads `.agents/agents/analyst.md` and can access the asset files; emulated only for bounded asset-manifest work the main Codex session can inspect directly; unsupported-with-gate when the task requires visual/audio inspection that the active Codex environment cannot perform. | May write only `assets/manifest.json`; never modify game code. |
| asset-producer | native when `spawn_agent(agent_type="worker", message=...)` can launch an official Codex worker with a message that loads `.agents/agents/asset-producer.md`, the scoped production unit, and required provider/tool references; unsupported-with-gate when the requested provider or isolated writable workspace is unavailable. | Write only the assigned asset unit and its declared reports; do not modify unrelated game code or dispatch sub-workers. |
| decomposer | native when `spawn_agent(agent_type="worker", message=...)` can launch an official Codex worker with a message that loads `.agents/agents/decomposer.md`; emulated by executing the decomposition package sequentially in the main Codex session. | Write only the owned artifact files for the package. |
| gdd-auditor | native when `spawn_agent(agent_type="worker", message=...)` can launch an official Codex worker with a message that loads `.agents/agents/gdd-auditor.md`; emulated by running the audit checklist sequentially in the main Codex session. | Read-only. Ask follow-up questions; do not edit the GDD. |

## Required Codex Delegation Context

Every delegated Codex role, native or emulated, must receive enough local
framework context to resolve the same files the lead session can resolve:

- project root and current working directory;
- `.agents/skills`;
- `.agents/agents`;
- `.agents/templates`;
- `.agents/godotmaker.yaml`;
- `.godotmaker/hooks`;
- selected stage instructions, including the current `$gm-*` skill and any
  `references/*.md` files named by that skill.

If any required context path is missing, stop before dispatch and report a
clear unsupported-with-gate. Do not silently continue with global or
Claude-specific paths.

## Codex Project-Local Skill And Agent Paths

Codex roles read project-local paths:

- skills from `.agents/skills/<name>/`;
- agent definitions from `.agents/agents/<name>.md`;
- templates from `.agents/templates/`;
- project config from `.agents/godotmaker.yaml`.

When a shared instruction refers to a GodotMaker skill name such as `gecs`,
`headless-build`, or `ui`, Codex must resolve it under `.agents/skills`.
Do not ask a Codex delegate to read Claude Code's skill tree.

## Worktree Strategy

Before any parallel worker dispatch, detect the current isolation state:

1. Determine the project root and run `git status --porcelain`.
2. Run `git worktree list --porcelain` and check whether the current path is
   already a linked worktree.
3. Detect detached-head or host-managed sandbox state with
   `git symbolic-ref --short -q HEAD`; an empty result means branch-oriented
   finish work may not be possible.

Then choose the first supported strategy:

1. **Existing isolation:** if the host already placed this role in an isolated
   workspace, use it and do not create or clean up another workspace.
2. **Runtime-native isolation:** if Codex `spawn_agent` supports an isolated
   workspace with the required context paths, use that for parallel workers.
3. **Git fallback:** if the repository is on a normal branch and git worktrees
   are allowed, create explicit worker worktrees from a clean snapshot. Include
   the required Codex context paths or fail before dispatch.
4. **Sequential emulation:** if isolation is unavailable but the tasks are
   independent and bounded, run one worker brief at a time in the main Codex
   session.
5. **Unsupported-with-gate:** if the stage requires parallel worker isolation
   and none of the above strategies is available, fail before the stage starts.

Do not clean up worktrees or sandboxes created by the host runtime. Only remove
git fallback worktrees that this stage created and tracked explicitly.

## Detached-Head And Sandbox Handoff

If Codex is running in detached HEAD, a read-only sandbox, or a host-managed
workspace that blocks branch, commit, push, or PR creation:

- finish the stage by writing the required project artifacts and report;
- do not attempt branch or PR operations from inside the delegate;
- tell the lead session which files changed and which commands passed;
- hand off branch, commit, push, or PR completion to the host application or
  parent session.

## Stage Gates

Fail before the stage starts when any of these are true:

- a required Codex context path is missing;
- the selected delegated role cannot be launched natively and cannot be
  emulated without violating its read/write rules;
- parallel worker isolation is required but neither native isolation nor safe
  git fallback is available;
- required verifier commands are blocked by sandbox or permission policy;
- analyst work requires visual/audio inspection that the active Codex runtime
  cannot perform.
