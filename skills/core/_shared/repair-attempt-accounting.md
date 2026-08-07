# Repair Attempt Accounting

This contract is shared by `gm-build` and `gm-fixgap`. Apply it separately to
each stable PLAN.md or GAP.md task ID. It never changes `stage.jsonl` gates or
allows an unverified task to complete.

## Counters and ledger

Keep the following record in the task's Notes (or its adjacent task ledger)
after **every** worker dispatch or handoff:

| Counter | Increment rule | Purpose |
|---|---|---|
| `dispatch_count` | Every worker dispatch, returned handoff, timeout, or replacement dispatch. | Observation only; it never fails a business task. |
| `repair_attempt_count` | Only a classified `effective_repair`. | The sole counter used by the five-attempt failure gate. |
| `no_progress_count` | Consecutive `incomplete_handoff` or `orchestration_failure` outcomes. | Detects orchestration trouble; it never fails a business task. |

Record for each dispatch: timestamp or sequence, worker/handoff outcome,
production diff files and summary, focused verification command/result, failure
fingerprint, classification, and all three counter values. Reset
`no_progress_count` to zero only after `effective_repair` or `verified_success`.
Do not reset `repair_attempt_count` while retrying the same task.

## Deterministic classification

Classify a handoff in this order. The lead makes the final classification from
the worker report and git diff; a worker's suggested classification is evidence,
not authority.

1. **`verified_success`**: the task has a relevant production diff and its
   focused verification passed. Do not increment `repair_attempt_count`; move
   through the normal task lifecycle.
2. **`effective_repair`**: increment `repair_attempt_count` by one only when
   all of these are true:
   - the current task produced an actual, relevant production implementation
     diff (not only tests, fixtures, tooling, configuration, or documents);
   - a focused verification for that task was actually run on that diff;
   - the verification completed normally and still failed because of the task's
     production behavior; and
   - the report records the command/output and a failure fingerprint (for
     example `test:<suite>::<case>:<assertion>` or
     `build:<file>:<line>:<diagnostic>`).

   Its production patch must be materially new or progressive relative to every
   already-counted repair. Replaying the same patch or merely restating an old
   fingerprint is not another effective repair.
3. **`incomplete_handoff`**: no increment to `repair_attempt_count`; increment
   `no_progress_count`. Use this for analysis-only work, no production diff,
   a `PARTIAL` handoff, or any code change that lacks focused verification.
4. **`orchestration_failure`**: no increment to `repair_attempt_count`;
   increment `no_progress_count`. Use this for a worker timeout/disconnect,
   forced immediate handoff, tool startup or test discovery/parser failure,
   environment/network/permission failure, or a repeated report with no new
   production repair.

Do not classify a test-infrastructure-only patch as `effective_repair` when the
task is a production-logic defect. A normal, task-relevant build or test failure
can qualify only when the failure is attributable to the changed production
behavior, rather than the command infrastructure.

## No-progress handling

At **3 consecutive** no-progress outcomes, stop automatic re-dispatch of the
same brief. Record an orchestration incident with the handoff evidence and
either re-dispatch with materially repaired context/ownership or escalate the
orchestration blocker. Keep the business task `pending` or `in_progress`; it
must not become `failed` because of this threshold.

## Five-repair gate

Only when `repair_attempt_count == 5` can the task be marked `failed` and
escalated to the user. The ledger must contain five materially distinct or
progressive production patches, each with focused verification that completed
normally, failed, and recorded its fingerprint. `dispatch_count` and
`no_progress_count` never satisfy this gate.

## Worker evidence contract

Every worker report must include `Repair Attempt Evidence` with the production
diff, focused verification, failure fingerprint, handoff condition, and a
suggested classification. Missing evidence is `incomplete_handoff`, not an
effective repair. See the worker report template for the exact fields.
