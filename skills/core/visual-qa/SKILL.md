---
name: visual-qa
description: |
  Visual quality assurance: analyze game screenshots for defects, compare against reference, check motion in frame sequences.
  Supports runtime-native inspection plus Gemini or OpenAI API-backed VQA.
context: fork
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

## Backend

Read `.godotmaker/config.yaml` for model selection:

- `vqa_model`: primary VQA backend. Supported values are `native`, `codex`, `gemini:<model>`, and `openai:<model>`.
- `vqa_fallback_model`: fallback when the primary backend is unavailable. Supported values are `native`, `codex`, and `none`.

Runtime-native VQA means direct image inspection by the selected runtime provider. `native` uses the active agent runtime. `codex` uses Codex image inspection, including from a Claude Code orchestration when Codex is available. API-backed VQA runs `${CLAUDE_SKILL_DIR}/scripts/visual_qa.py` with `--model <vqa_model>`. Do not silently switch providers except for the explicit `vqa_fallback_model` path.

Argument flags override config for a single call:

- `--native`: use runtime-native image inspection only.
- `--gemini`: run the script with the configured Gemini selector, or `gemini:gemini-2.5-flash` if config uses another provider.
- `--openai`: run the script with the configured OpenAI selector, or `openai:gpt-5.5` if config uses another provider.
- `--both`: run native first, then the configured API-backed model. Aggregate verdicts.

## Mode Detection

If arguments include `--log <path>`, set `VQA_LOG` to that path and remove
those tokens before mode detection.

Pick the mode from caller args by matching the first row whose precondition holds. If no row matches, STOP and tell the caller their args are malformed — do not fall back to a different mode.

| Mode | Precondition (in args) | Required argv shape |
|---|---|---|
| Static | `references/<ref>.png` path AND exactly 1 `e2e/screenshots/<shot>.png` path | `Check references/<ref>.png against e2e/screenshots/<shot>.png — Goal: ... Requirements: ... Verify: ...` |
| Dynamic | `references/<ref>.png` path AND ≥2 frame paths (`e2e/screenshots/<dir>/frame_*.png`) | `Check references/<ref>.png against <frame_glob> — Goal: ... Requirements: ... Verify: ...` |
| Question | No `references/` path; caller asks a question about screenshots | `--question "..." <screenshot.png> [...]` |

If a reference path appears in the args but the file does not exist on disk → STOP. Return `verdict: error` with `reason: "reference file missing: <path>"`.

Reject any other argv shapes (`--screenshot <file> --requirements "..."` and similar).

## Runtime-Native Execution

Read every image file referenced in the arguments using the active runtime image-reading path. Analyze using the criteria and output format below. Never look at code — only images.

After producing output, append a debug log entry:

```bash
printf '{"ts":"%s","mode":"MODE","model":"native","query":"QUERY","files":["FILE1","FILE2"],"output":"FIRST_LINE..."}\n' \
  "$(date -u +%Y-%m-%dT%H:%M:%SZ)" >> "${VQA_LOG:-.vqa.log}"
```

## API-Backed Execution

Parse the arguments to construct the command. The script is at `${CLAUDE_SKILL_DIR}/scripts/visual_qa.py`.

First, detect the available Python command — run `python3 --version` and `python --version`, then use whichever succeeds. Cache the result for the session.

**Model selection:** Check `.godotmaker/config.yaml` for `vqa_model`. If present and API-backed (`gemini:<model>` or `openai:<model>`), pass it as `--model <value>`. If the file or field does not exist, omit `--model` (the script defaults to `gemini:gemini-2.5-flash`). If `vqa_model` is `native` or `codex`, use runtime-native execution instead of the script unless an explicit API flag was requested.

```bash
# Read model from config (if exists)
VQA_MODEL=$(grep -oP 'vqa_model:\s*\K\S+' .godotmaker/config.yaml 2>/dev/null || echo "")
MODEL_FLAG=""
case "$VQA_MODEL" in
  native|codex|"") MODEL_FLAG="" ;;
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

(`PYTHON` = whichever command worked above.) Always pass `--log`. Use `.vqa.log` unless the caller provides a log path. Print the script output as your response.

If the configured API-backed model is unavailable and `vqa_fallback_model` is `native` or `codex`, switch to Runtime-Native Execution and record the fallback in the log entry's `model` field. If `vqa_fallback_model` is `none`, stop with an error instead of silently changing providers.

## Aggregated Mode (`--both`)

1. Read all images with Read tool, do runtime-native analysis using criteria below
2. Run the configured API-backed script, capture output
3. Produce combined verdict:
   - Either says `fail` → `fail`
   - Either says `warning` and neither `fail` → `warning`
   - Both `pass` → `pass`
4. Merge issue lists from both, deduplicate by location + description
5. Label each issue source: `[api]`, `[native]`, or `[both]`
6. Log both outputs to `.vqa.log`

## Analysis Criteria

## Acceptance Gate Rules

Use these rules before choosing the final verdict:

- `fail` means an acceptance criterion is not visibly satisfied, or a
  visual/logical/motion bug blocks readability, operation, state truth, or
  layout stability.
- `warning` means the acceptance criteria pass, and a material non-blocking
  issue was observed while checking the caller-provided context. Do not expand
  the review scope to search for warnings.
- `pass` means the acceptance criteria pass and remaining differences are
  minor/style-only.
- If Task Context and reference disagree, evaluate against Task Context and
  mention the disagreement.
- Pure reference/style mismatch should be a `note`, not a failing verdict.
- Evaluate visible screenshots and caller-provided `Verify:` criteria only.
  Do not infer prior play history unless `Verify:` asks for it.

### Implementation Quality (static + dynamic)

Assets are usually fine — what breaks is how they're placed, scaled, composed.
Flag these as `fail` only when they block acceptance, readability, operation,
state truth, or layout stability:
- Grid/uniform placement when reference shows organic arrangement
- Uniform/default scale when reference shows varied, purposeful sizing
- Flat composition when reference has depth and layering
- Stretched, tiled, or carelessly applied materials
- Objects unrelated to environment (just placed on a flat plane)
- Camera framing doesn't match required context or blocks readability/operation

### Visual Bugs

- Z-fighting (flickering overlapping surfaces)
- Texture stretching, tiling seams, missing textures (magenta/checkerboard)
- Geometry clipping (objects visibly intersecting)
- Floating objects that should be grounded
- Shadow artifacts (detached, through walls, missing)
- Lighting leaks through opaque geometry
- Culling errors (missing faces, disappearing objects)
- UI overlap, truncated text, offscreen elements

### Logical Inconsistencies

- Impossible orientations (sideways, upside-down, embedded in terrain)
- Scale mismatches (tree smaller than character, door too small)
- Misplaced objects (furniture on ceiling, rocks in sky)
- Broken spatial relationships (bridge not connecting, stairs into wall)

### Placeholder Remnants

- Untextured primitives contrasting with surrounding detail
- Default Godot materials (grey StandardMaterial3D, magenta missing shader)
- Debug artifacts in normal gameplay captures (nav mesh, axis gizmos, visible
  collision shapes)
- Collision overlay mismatch in `--debug-collisions` captures (shape offset,
  wrong size, or wrong shape type relative to the sprite)

### Motion & Animation (dynamic mode only)

Compare consecutive frames (0.5s apart):
- Stuck entities (same position/pose across frames when movement expected)
- Jitter/teleportation (large position jumps between frames)
- Sliding (position changes but pose frozen — ice-skating)
- Physics breaks (objects through walls, endless bouncing, unnatural acceleration)
- Animation mismatches (walk anim at running speed, idle while moving)
- Camera issues (sudden jumps, clipping through geometry)
- Collision failures (overlapping objects that should collide)

## Output Format

### Static / Dynamic

```
### Verdict: {pass | fail | warning}

### Reference Match
{1-3 sentences: does the game capture the reference's *intent* — placement logic, scaling, composition, camera? Distinguish acceptance-blocking implementation shortcuts from asset/engine limitations.}

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

Severity: major = must fix. minor = non-blocking, record only. note = cosmetic/style-only, can ship.

### Question Mode

```
### Answer
{Direct, specific, actionable answer. Reference locations, frames, colors, objects.}

### Visual Evidence
{What in the screenshots supports the answer. Reference specific frames and locations.}
```
