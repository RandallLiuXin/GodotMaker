---
name: gm-verify
description: |
  Mechanical verification of the built game: headless build, unit tests, lint, static checks.
  Explicit invocation only — use /gm-verify.
disable-model-invocation: true
---

# GodotMaker Verify

$ARGUMENTS

You are performing mechanical verification of a built Godot game project. This is a non-creative, checklist-driven process.

## Session Setup

**FIRST ACTION — before anything else:** Write `verify` to `.godotmaker/current_role`.

**Permission:** Read-only with three exceptions — you may write `.godotmaker/current_role`, append to `.godotmaker/stage.jsonl`, and write `.godotmaker/verify_report.json`. Verify never modifies game code or planning docs.

## Resume Check

Read `.godotmaker/stage.jsonl` (treat as empty if missing) — each line is `{"role": X, "ts": Y}`.

- If **no event with `role == "build"` AND no event with `role == "fixgap"`** exists anywhere in the file → STOP. Tell user to run `/gm-build` first.
- If the **last event** has `role == "verify"` → STOP. Tell the user:
  > "Verify already ran at {timestamp} with no state-changing event since. Recommended next: /gm-evaluate.
  > If you need to redo this step or have other plans, just tell me."
- Otherwise → proceed (verify is naturally re-invoked after each build/fixgap cycle).

## Run the checks

From the project root:

```bash
python tools/run_verify.py
```

`run_verify.py` wraps the four mechanical checks (build / unit tests /
lint / static check) and prints a JSON document matching `Output Format`
Section B to stdout. Capture stdout.

What the script does:

- Selects one of the supported backend pairs from `.godotmaker/config.yaml`:
  **GDScript + gdUnit** or **C# + dotnet test**. `language_backend` and
  `unit_test_backend` may be explicit or `auto`; ambiguous detection is a
  tooling error, never a silent fallback.
- Reads `godot_path` from `.claude/godotmaker.yaml`; falls back to plain
  `godot` from PATH. A missing or broken binary surfaces as a
  `tooling_notes[].suggested_fallback = "escalate"` entry.
- For GDScript, runs the existing Godot headless build and gdUnit command,
  parsing JUnit XML as before.
- For C#, runs `dotnet build <dotnet_target>`, builds the declared
  `godot_csharp_project` separately when needed, then runs Godot Mono
  headless. Unit tests run through `dotnet test --no-build --no-restore
  --logger trx`; the runner parses every generated TRX file rather than
  trusting stdout.
- Stubs `checks.lint` as `pass` with `format_drift: null`. Do NOT re-enable
  here.
- Delegates common static checks to `check_project.py`. GDScript projects
  also run gecs Component/System and gdUnit discovery. C# projects report
  those checks as **SKIP / N/A** in `checks.static_check.skipped_checks`;
  they are not counted as passed checks.
- Exit code 0 = ran to completion (per-check pass/fail is in the JSON).

## Sanity-check the script output

Before writing the report, validate. Block on any of these:

- JSON does not parse, or any of `result` / `ts` / `checks` /
  `tooling_notes` is missing
- Any of the four `checks.{build,unit_tests,lint,static_check}`
  entries is absent
- `result == "pass"` but `tooling_notes` is non-empty — re-run or escalate
- `checks.unit_tests.passed + .failed + .skipped == 0` — spot-check with the
  backend-selected command: gdUnit with `--report-directory <temp>`, or
  `dotnet test` with a fresh TRX results directory.
- Any `tooling_notes` entry whose `crashed_on` looks unrelated to the
  failing check

If any block fires, diagnose by running the implicated command
yourself, then either re-run `run_verify.py` or surface the issue
verbatim to the user. Do NOT silently rewrite the script's output.

## Output Format

You produce **two outputs**:

### A. Human-readable report (chat)

Build this from the JSON the script returned — do not re-run any
command for the chat side.

```
## Verification Report

### Build
Backend: GDScript | C#
Result: PASS | FAIL
{If FAIL, one line per checks.build.errors[] entry: `- {file}:{line}: {message}` (file/line may be empty)}

### Unit Tests
Framework: gdunit | dotnet
Result: PASS | FAIL
{N passed, M failed, K skipped}
{If FAIL, one line per checks.unit_tests.failures[]: `- {test}: {message}`}

### Lint
Status: SKIP (gdtoolkit disabled — ROADMAP R-112)

### Static Check
Result: PASS | FAIL
{If FAIL, one line per checks.static_check.issues[]: `- {check}: {detail}`}
{For each skipped check: `- SKIP / N/A: {check}: {reason}`}

### Overall: PASS | FAIL

{If tooling_notes is non-empty, append:
## Tooling Notes
- {tool}: {error} (suggested_fallback: {suggested_fallback})
…}
```

### B. Machine-readable report (`.godotmaker/verify_report.json`)

Write this file every run (PASS or FAIL). `/gm-build` and `/gm-fixgap` read it on their next invocation to translate failures into pending tasks.

Schema:

```json
{
  "result": "pass | fail",
  "ts": "<UTC ISO 8601 timestamp, e.g. 2026-05-07T14:23:00Z>",
  "backend": {
    "language": "gdscript | csharp",
    "unit_tests": "gdunit | dotnet",
    "selection": "config | auto | legacy-default",
    "dotnet_target": null,
    "godot_csharp_project": null
  },
  "checks": {
    "build": {
      "result": "pass | fail | error",
      "errors": [
        {"file": "src/foo.gd", "line": 42, "message": "Identifier 'bar' not declared"}
      ]
    },
    "unit_tests": {
      "result": "pass | warn | fail | error",
      "framework": "gdunit | dotnet",
      "total": 624,
      "passed": 624,
      "failed": 0,
      "skipped": 0,
      "failures": [
        {"test": "test_player_input::test_jump", "message": "expected 10, got 0"}
      ],
      "warnings": [
        "Found 4 possible orphan nodes."
      ]
    },
    "lint": {
      "result": "pass | warn | fail | error",
      "issues": [
        {"file": "src/foo.gd", "rule": "max-line-length", "message": "line too long"}
      ],
      "format_drift": {
        "file_count": 92,
        "command": "gdformat src/ test/ scenes/"
      }
    },
    "static_check": {
      "result": "pass | fail | error",
      "issues": [
        {"check": "missing_unit_test", "detail": "s_level_up_overlay has no test"}
      ],
      "skipped_checks": [
        {"check": "gdscript_gecs", "reason": "N/A for language_backend=csharp"}
      ]
    }
  },
  "tooling_notes": [
    {
      "tool": "gdlint",
      "crashed_on": "src/foo.gd",
      "error": "NotImplementedError at gdtoolkit/linter/class_checks.py:144",
      "suggested_fallback": "exclude_file",

      "narrowed_command": null,
      "rule_name": null,
      "check_name": null
    }
  ]
}
```

Field rules:

- **Top-level `result`** — `"pass"` iff every `checks.*.result` ∈ {`pass`, `warn`}. Any `fail` / `error` makes overall `fail`. `tooling_notes` alone never makes overall `fail` — the `error` it pairs with does.
- **`ts`** — UTC ISO 8601 at the moment you write the file. Consumers compare it against their own last-event timestamp for freshness.
- **All array fields are required** (possibly empty `[]`). Do not omit them.
- **Per-check `result`** — `pass` / `fail` are project-content. `warn` is non-blocking diagnostic noise (lint style drift or gdUnit warnings such as orphan nodes when every assertion passed). `error` means the tool itself crashed and the project's actual state is unknown for this check; pair `error` with exactly one `tooling_notes` entry. Consumers fix `error` via config, NOT project code.
- **`format_drift`** — object when `gdformat --check` reports drift; `null` otherwise.
- **`suggested_fallback`** + matching operand — the producer fills the operand so the consumer can act deterministically:

  | `suggested_fallback` | Required operand |
  |---|---|
  | `exclude_file` | `crashed_on` (already required on every note) |
  | `scope_narrow` | `narrowed_command` (replacement command, e.g. `"gdlint src/"`) |
  | `add_gdlintrc_rule` | `rule_name` (e.g. `"class-name"`) |
  | `skip_check` | `check_name` (e.g. `"missing_unit_test"`) |
  | `escalate` | — (none) |

  **Producer rule:** if you cannot fill the required operand for a non-`escalate` fallback, emit `escalate` instead.

  **Consumer rule** (open-enum forward-compat): a missing required operand or an unknown `suggested_fallback` value MUST be treated as `escalate` (surface to user, do NOT auto-fix). Never crash.

## On Failure

When the script's JSON has `result: "fail"`:

1. Write the script's JSON verbatim to `.godotmaker/verify_report.json`.
2. Emit the chat report (Section A) and tell the user which checks failed. Suggest `/gm-build` if the last state-changing event was `build`, `/gm-fixgap` if it was `fixgap`.
3. Do NOT append a `verify` event to `stage.jsonl` — only PASS records a stage event.

## When Done

When the script's JSON has `result: "pass"`:

1. Write the script's JSON verbatim to `.godotmaker/verify_report.json`. (Field rules apply: `tooling_notes == []`, all `checks.*.result` ∈ {`pass`, `warn`} — the script enforces these but spot-check them once more before writing.)
2. From the project root run `python tools/append_stage_event.py verify` to append a `{"role": "verify", "ts": "<server-generated UTC>"}` line to `.godotmaker/stage.jsonl`. Do NOT hand-write the JSON or the timestamp — the helper exists so the timestamp comes from the system clock, not your own output.
3. `git add -A && git commit -m "chore(verify): <Tag>"`
4. Inform the user: `Verify complete. Recommended next: /gm-evaluate`
