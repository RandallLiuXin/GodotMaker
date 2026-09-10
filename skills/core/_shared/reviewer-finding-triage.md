# Reviewer Finding Triage

After the reviewer subagent reports back, the dispatching role
(gm-build / gm-fixgap) decides per finding what to do with it. The reviewer
finds issues and assigns severity; it does not perform triage.

## Three options per finding

Every finding gets exactly one of:

- **ACCEPT** — the finding is real and worth fixing. Add a NEW `pending`
  task to the active task file (`PLAN.md` for gm-build, `GAP.md` for
  gm-fixgap).
- **REJECT** — the finding is wrong (false positive). Do not create a task.
- **SKIP** — the finding is real but not worth fixing now. Do not create a task.

## Defaults (when uncertain)

- **critical / major** → default ACCEPT. Treat REJECT and SKIP as
  exceptions that need justification.
- **minor** → default SKIP.

## Citation requirement

| Severity         | REJECT      | SKIP        |
|------------------|-------------|-------------|
| critical / major | **Required**| **Required**|
| minor            | Optional    | Optional    |

A mandatory citation must be ONE of:

- A specific gotcha entry (e.g., `.claude/skills/gecs/gotchas.md` G7)
- A specific Godot/ECS API doc reference
- A prior `MEMORY.md` architecture decision or project constraint
- A `PLAN.md` / `GAP.md` task that already covers the same issue (by task ID)

The citation must actually support the decision — do not cite a document you
have not read or a gotcha that does not match.

### Forbidden REJECT reasons (regardless of severity)

- "Code looks correct to me"
- "Worker tested it and it passed"
- "Reviewer is wrong" (without citation)
- "Already verified" (without pointing to the verifier's specific check)

If you cannot satisfy the citation requirement for a critical/major finding,
**ACCEPT** it.

## Persistence boundary

Do not persist raw findings, REJECT/SKIP decisions, or their rationale in
`MEMORY.md`. Reviewer output is runtime evidence, not durable project memory.

If a finding reveals a stable module boundary, ownership rule, dependency, or
project constraint, record only that normalized architecture or constraint in
`MEMORY.md`. Do not copy the finding or triage history into the entry.
