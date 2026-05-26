---
name: visual-qa
description: |
  Visual quality assurance: analyze game screenshots for defects, compare against reference, check motion in frame sequences.
  Supports runtime-native inspection plus Gemini or OpenAI API-backed VQA.
---

# Visual QA

$ARGUMENTS

CRITICAL: Find acceptance-blocking problems. Do not rationalize defects that
block the caller-provided Task Context.

CRITICAL: When Task Context is provided, use its `Verify:` criteria as the
gate. Treat the reference image as visual intent, not as a pixel-perfect or
style-matching gate. Do not fail a check for pure reference/style mismatch
(palette, capitalization, wording, roundedness, spacing, polish) unless it
breaks the `Verify:` criteria or makes the scene unreadable, unusable, visually
ambiguous, or logically false.

## Execution Steps

### Step 1 - Parse Arguments

If arguments include `--log <path>`, set `VQA_LOG` to that path and remove
those tokens before mode detection.

Reject unsupported argv shapes such as `--screenshot <file> --requirements "..."`.

### Step 2 - Detect Mode

Pick the mode from caller args by matching the first row whose precondition
holds. If no row matches, STOP and tell the caller their args are malformed.

| Mode | Precondition | Required argv shape |
|---|---|---|
| Static | `references/<ref>.png` path AND exactly 1 `e2e/screenshots/<shot>.png` path | `Check references/<ref>.png against e2e/screenshots/<shot>.png - Goal: ... Requirements: ... Verify: ...` |
| Dynamic | `references/<ref>.png` path AND 2 or more frame paths (`e2e/screenshots/<dir>/frame_*.png`) | `Check references/<ref>.png against <frame_glob> - Goal: ... Requirements: ... Verify: ...` |
| Question | No `references/` path; caller asks a question about screenshots | `--question "..." <screenshot.png> [...]` |

If a reference path appears in the args but the file does not exist on disk,
STOP. Return `verdict: error` with `reason: "reference file missing: <path>"`.

Each call takes one scene's reference plus that scene's screenshot or frame
paths. Reject a single stitched, montage, or contact-sheet image supplied in
place of per-scene paths.

### Step 3 - Select Backend

Read `.godotmaker/config.yaml` for model selection:

- `vqa_model`: primary VQA backend. Supported values are `native`, `codex`, `gemini:<model>`, and `openai:<model>`.
- `vqa_fallback_model`: fallback when the primary backend is unavailable. Supported values are `native`, `codex`, and `none`.

If `.godotmaker/config.yaml` is missing, `vqa_model` is missing, or
`vqa_model` is empty, STOP with `verdict: error`.

Runtime-native VQA means direct image inspection by the selected runtime
provider. `native` uses the active agent runtime. `codex` uses Codex image
inspection, including from a Claude Code orchestration when Codex is available.
API-backed VQA runs `${CLAUDE_SKILL_DIR}/scripts/visual_qa.py` with
`--model <vqa_model>`.

Do not silently switch providers except for the explicit `vqa_fallback_model`
path.

### Step 4A - Runtime-Native Execution

Use this path when `vqa_model` is `native` or `codex`, or when an API-backed
model fails and `vqa_fallback_model` is `native` or `codex`.

1. Confirm the mode detected in Step 2.
2. Read the mode prompt:
   - Static: `scripts/static_prompt.md`
   - Dynamic: `scripts/dynamic_prompt.md`
   - Question: `scripts/question_prompt.md`
3. For Static and Dynamic, read `scripts/criteria.md`.
4. Combine the mode prompt, criteria, and Task Context.
5. Read every image file referenced in the arguments using the active runtime
   image-reading path.
6. Analyze only the supplied images and constructed prompt. Never inspect game
   code.
7. Produce the required output format.
8. Append the debug log entry.

For `native`, use the active agent runtime's image inspection. For `codex`, use
Codex image inspection.

### Step 4B - API-Backed Execution

Use this path when `vqa_model` is `gemini:<model>` or `openai:<model>`.

Parse the arguments to construct the command. The script is at
`${CLAUDE_SKILL_DIR}/scripts/visual_qa.py`.

Detect the available Python command: run `python3 --version` and
`python --version`, then use whichever succeeds. Cache the result for the
session.

Model selection:

- If `vqa_model` is API-backed, pass it as `--model <value>`.
- If `vqa_model` is `native` or `codex`, use Step 4A.
- If `vqa_model` is missing or empty, STOP with `verdict: error`.

```bash
VQA_MODEL=$(grep -oP 'vqa_model:\s*\K\S+' .godotmaker/config.yaml 2>/dev/null || echo "")
MODEL_FLAG=""
case "$VQA_MODEL" in
  "") echo "Missing vqa_model in .godotmaker/config.yaml" >&2; exit 1 ;;
  native|codex) echo "Use Runtime-Native Execution for vqa_model: $VQA_MODEL" >&2; exit 1 ;;
  gemini:*|openai:*) MODEL_FLAG="--model $VQA_MODEL" ;;
  *) echo "Unsupported vqa_model for API-backed visual_qa.py: $VQA_MODEL" >&2; exit 1 ;;
esac

# Static
PYTHON ${CLAUDE_SKILL_DIR}/scripts/visual_qa.py --log ${VQA_LOG:-.vqa.log} $MODEL_FLAG [--context "Goal: ... Requirements: ... Verify: ..."] reference.png screenshot.png

# Dynamic
PYTHON ${CLAUDE_SKILL_DIR}/scripts/visual_qa.py --log ${VQA_LOG:-.vqa.log} $MODEL_FLAG [--context "..."] reference.png frame1.png frame2.png ...

# Question
PYTHON ${CLAUDE_SKILL_DIR}/scripts/visual_qa.py --log ${VQA_LOG:-.vqa.log} $MODEL_FLAG --question "the question" screenshot.png [frame2.png ...]
```

Always pass `--log`. Use `.vqa.log` unless the caller provides a log path.
Print the script output as your response.

If the configured API-backed model is unavailable and `vqa_fallback_model` is
`native` or `codex`, switch to Step 4A and record the fallback in the log entry's
`model` field. If `vqa_fallback_model` is `none`, stop with an error.

### Step 5 - Log Runtime-Native Output

After runtime-native execution produces output, append a debug log entry:

```bash
printf '{"ts":"%s","mode":"MODE","model":"MODEL","query":"QUERY","files":["FILE1","FILE2"],"output":"FIRST_LINE..."}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${VQA_LOG:-.vqa.log}"
```

Set `MODEL` to the `vqa_model` or `vqa_fallback_model` value used for the call.

## Analysis Criteria

Read `scripts/criteria.md` before choosing the final verdict.

## Output Format

### Static / Dynamic

```text
### Verdict: {pass | fail | warning}

### Reference Match
{1-3 sentences: does the game capture the reference's intent: placement logic, scaling, composition, camera?}

### Goal Assessment
{1-3 sentences from Task Context. "No task context provided." if none.}

### Issues

{If none: "No issues detected." Otherwise:}

#### Issue {N}: {short title}
- **Type:** style mismatch | visual bug | logical inconsistency | motion anomaly | placeholder
- **Severity:** major | minor | note
- **Acceptance impact:** blocks acceptance | non-blocking | style-only
- **Frames:** {dynamic only: which frames}
- **Location:** {where in frame}
- **Description:** {1-2 sentences}

### Summary
{One sentence.}
```

Severity: major = must fix. minor = non-blocking, record only. note =
cosmetic/style-only, can ship.

### Question Mode

```text
### Answer
{Direct, specific, actionable answer. Reference locations, frames, colors, objects.}

### Visual Evidence
{What in the screenshots supports the answer. Reference specific frames and locations.}
```
