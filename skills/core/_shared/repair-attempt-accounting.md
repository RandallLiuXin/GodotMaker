# Repair Attempt Accounting

Apply this contract separately to each stable PLAN.md or GAP.md task ID. Do not
change `stage.jsonl` gates.

## Counters

| Counter | Increment |
|---|---|
| `dispatch_count` | Every worker dispatch, handoff, timeout, or replacement dispatch. |
| `repair_attempt_count` | Each `effective_repair`. |
| `no_progress_count` | Each consecutive `incomplete_handoff` or `orchestration_failure`. |

After every handoff, record sequence, production diff, focused verification
command/result, failure fingerprint, classification, and all counter values in
the task's Notes. Reset `no_progress_count` after `effective_repair` or
`verified_success`. Do not reset `repair_attempt_count` while retrying.

## Classification

1. `verified_success`: production diff and focused verification pass. Do not
   increment `repair_attempt_count`.
2. `effective_repair`: increment `repair_attempt_count` only when all apply:
   - relevant production implementation diff;
   - focused verification ran on that diff and failed normally;
   - command/output and failure fingerprint recorded;
   - patch is materially new or progressive from every counted repair.
3. `incomplete_handoff`: do not increment `repair_attempt_count`; increment
   `no_progress_count`. Apply to analysis-only work, no production diff,
   `PARTIAL`, or missing focused verification.
4. `orchestration_failure`: do not increment `repair_attempt_count`;
   increment `no_progress_count`. Apply to timeout/disconnect, forced handoff,
   tool startup, test discovery/parser, environment/network/permission failure,
   test-infrastructure-only changes for a production-logic task, or repeated
   report without a new production repair.

## No-progress threshold

At 3 consecutive no-progress outcomes, stop automatic re-dispatch of the same
brief. Record an orchestration incident. Re-dispatch with revised context or
ownership, or escalate the blocker. Keep the business task `pending` or
`in_progress`; do not mark it `failed`.

## Failure gate

Mark a task `failed` only when `repair_attempt_count == 5`. Record five
distinct or progressive production patches, focused verification failures, and
failure fingerprints. Do not use `dispatch_count` or `no_progress_count` for
this gate.

## Report fields

Require: production diff, focused verification, failure fingerprint, handoff
condition, and suggested classification. Treat missing fields as
`incomplete_handoff`.
