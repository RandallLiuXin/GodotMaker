# Reviewer Dispatch Protocol

Dispatch a reviewer **once per build/fixgap cycle**, after every task in `PLAN.md` (build) or `GAP.md` (fixgap) has reached `completed` status and the verifier has just passed. The reviewer assesses the integrated state, not individual workers' output. The reviewer decides which domain-specific reviewer skills to run.

**Agent definition:** `.claude/agents/reviewer.md` — system prompt loaded automatically via `subagent_type: "reviewer"`.

## Agent Call

```
Agent({
  subagent_type: "reviewer",
  description: "Reviewer: review {task_name}",
  model: "{reviewer_model from .godotmaker/config.yaml, default: sonnet}",
  prompt: "{reviewer brief below}"
})
```

## Reviewer Brief Template

```
## Review: {what was implemented}                       [REQUIRED]

### Project Path                                         [REQUIRED]
{Absolute path to the Godot project}

### Files to Review                                      [REQUIRED]
- {file path}: {what it contains}

### Context                                              [REQUIRED]
{What the system does, which Components/Systems are involved}

### Specific Concerns                                    [OPTIONAL]
{Anything you want the reviewer to pay special attention to}

### Asset Runtime Snapshot                               [REQUIRED when files use visual assets]
{Resolve each required asset from the authoritative catalog and paste only the
snapshot objects emitted by:

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --snapshot --asset-id <asset_id>
```

Each object contains only `asset_id`, `godot_artifact.type`, and
`godot_artifact.path`.
Do not add source layouts, frame data, atlas regions, provider evidence, or
support metadata paths. Describe required animation behavior or temporary-FX
lifecycle in `Context`, not in the snapshot.}
```

## Handling the Reviewer's Report

The dispatching role decides per finding what to do with it. See
`references/reviewer-finding-triage.md` for the full rules and the
triage record format.

Quick summary — every finding gets one of:
- **ACCEPT** → add a fix task to `PLAN.md` (gm-build) or `GAP.md` (gm-fixgap).
- **REJECT** → finding is wrong; record in `MEMORY.md` "Reviewer Triage Log".
- **SKIP** → finding is real but not worth fixing now; same MEMORY.md section.

Defaults when uncertain: critical/major → ACCEPT; minor → SKIP.
Citation is required for critical/major REJECT/SKIP; optional for minor.

The reviewer itself does NOT know about the triage — its job is to
report findings honestly with severity. Triage is the dispatching role's
responsibility.
