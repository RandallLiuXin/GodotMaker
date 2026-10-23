# GodotMaker Agent Operation Contract

This is the canonical runtime-independent operation contract for the published
GodotMaker pipeline and its supporting skills. Runtime mappings under
`agent-runtimes/<agent>/references/runtime-mapping.md` must contain every
operation in this table exactly once.

Each runtime mapping classifies an operation as exactly one of:

- `native`: the runtime directly provides the invocation path.
- `emulated`: GodotMaker provides a documented adapter or fallback with the
  same user-visible result.
- `gated`: the invocation path works only after a stated precondition; the
  stage must stop before dependent work when the precondition is not met.
- `unsupported`: no contract-compliant invocation path exists for that
  runtime. A dependent stage must stop and name a supported alternative.

## Canonical Operations

| Operation | Contract |
|---|---|
| `invoke_stage` | Run a GodotMaker stage entrypoint such as scaffold, gdd, asset, build, verify, evaluate, fixgap, accept, or finalize through the selected runtime's stage invocation surface. |
| `invoke_supporting_skill` | Load a published supporting skill in the current session without assuming another runtime's command syntax or tool name. |
| `read_project_config` | Read the selected runtime's published project configuration to discover `godot_path`, project settings, and runtime roots before executing a dependent operation. |
| `read_skill_reference` | Resolve references, templates, scripts, tools, and bundled docs relative to the active published skill directory. No skill may depend on a Claude-only skill-root token. |
| `dispatch_worker` | Run an implementation worker with the required role definition, brief, file ownership, isolation, and report contract. |
| `dispatch_reviewer` | Run independent review against integrated work while preserving the reviewer report and triage contract. |
| `dispatch_verifier` | Run verification while preserving the verifier report and failure-to-task conversion contract. |
| `dispatch_analyst` | Run image/audio asset inspection with the analyst role and its restricted input/output contract. |
| `dispatch_asset_producer` | Run one generated-asset production unit with the asset-producer role and selected provider contract. |
| `dispatch_decomposer` | Run GDD decomposition packages with the decomposer role and declared owned files. |
| `dispatch_gdd_auditor` | Run an independent GDD audit pass with the gdd-auditor role and bounded question contract. |
| `track_plan` | Maintain visible session task state for multi-step work, separate from project artifacts such as `PLAN.md` and `GAP.md`. |
| `ask_user_question` | Ask an interactive question when possible, or use the documented non-interactive gate/fallback without inventing an answer. |
| `classify_repair_attempt` | Apply `repair-attempt-accounting.md` to distinguish dispatch count from evidence-complete production repair attempts. |
| `inspect_images` | Execute the selected VQA or analyst image-inspection route, including runtime-native, Codex-selected, or API-backed paths, and produce the required report/log. |
| `generate_images` | Execute the selected image provider route and preserve the generated-path claim and provider report contracts. |
| `run_shell_command` | Execute local framework/project commands with the correct working directory and report exit status, important output, skips, and failures honestly. |
| `access_godot_mcp` | Reach the runtime's Godot inspection path, whether a registered MCP server or a documented equivalent adapter, and fail closed when it is unavailable. |
| `apply_permission_policy` | Apply the selected runtime's permission, sandbox, trust, role-lock, and hook rules without deadlocking expected framework commands or bypassing denials. |
| `forward_hook_context` | Preserve non-blocking hook `additionalContext` in the active session when that runtime installs a hook adapter; do not silently discard returned guidance. |
| `detect_worktree_state` | Detect normal checkout, linked worktree, isolated host workspace, detached HEAD, or sandbox state before delegation and finish decisions. |
| `create_or_use_isolated_workspace` | Create, reuse, or deliberately avoid isolation while ensuring published runtime resources are available to delegated work. |
| `finish_branch_or_handoff` | Finish through the safe branch/commit/push/PR or host handoff path allowed by the current checkout and permission state. |

## Mapping Rules

Every runtime mapping must use a three-column `Operation | Class | Invocation
path` table. The operation column must equal this canonical set: no omissions,
duplicates, or runtime-only operation names. Explanatory sections may add
constraints, but may not silently change the table's classification or path.

When an operation is `gated` or `unsupported`, stop before making changes that
depend on it and report the smallest setup change or handoff that can continue.
