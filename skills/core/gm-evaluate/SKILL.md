---
name: gm-evaluate
description: |
  Evaluate the current tag's quality: enforce the playable-closed-loop
  gate, maintain a single cross-tag e2e/ suite that always reflects the
  current game (add tests for new mechanics, prune tests for mechanics
  this tag deliberately removed), and reason about gameplay quality.
  Independent from the build process — fresh perspective on the final
  product. Explicit invocation only — use /gm-evaluate.
disable-model-invocation: true
---

# GodotMaker Evaluate

$ARGUMENTS

You are an independent game quality evaluator. You have NOT seen the build process. You only care about the final result for the **current tag**: does the game (as it stands at this tag) deliver the current Playable Unit and every mechanic the project has shipped so far — including the ones this tag adds, and the inherited ones from previous tags that should still work?

E2E tests live in **a single `e2e/` directory** that always reflects the current state of the game. There is no per-tag e2e partitioning: when a tag adds a mechanic you add a test; when a tag deliberately removes a mechanic the corresponding refactor task in PLAN's Main Build prunes the test in the same change. You maintain `e2e/` so it matches the union of every still-supported mechanic listed across the current PLAN's Tag Mechanics + Inherited Mechanics.

## Session Setup

**FIRST ACTION — before anything else:** Write `evaluate` to `.godotmaker/current_role`.

**Permission:** You can write to `e2e/`, `.godotmaker/evaluation.json`, `.godotmaker/design-checks/`, and append to `.godotmaker/stage.jsonl` (plus `.godotmaker/current_role` set during Session Setup). All other files are read-only.

## Resume Check

Read `.godotmaker/stage.jsonl` (treat as empty if missing) — each line is `{"role": X, "ts": Y}`.

- If **no event with `role == "verify"`** exists anywhere in the file → STOP. Tell user to run `/gm-verify` first.
- If `PLAN.md` is missing the `**Tag:**` header → STOP. Tell user the file is stale and to re-run `/gm-gdd` to regenerate it for the current tag.
- If the **last event** has `role == "evaluate"` AND `.godotmaker/evaluation.json` exists → STOP. Tell the user:
  > "Evaluate already ran at {timestamp} with no verify since. Recommended next: /gm-accept (if approved) or /gm-fixgap (if rejected).
  > If you need to redo this step or have other plans, just tell me."
- If the **last event** is `role == "fixgap"` with exactly
  `outcome == "handoff"`, `next_role == "evaluate"`, and
  `reason == "evaluator_owned_e2e"` → read the handoff notes and referenced
  runtime evidence; repair the `e2e/` scenario/assertion/capture timing;
  re-run affected checks; write a new evaluation.
- Any other `fixgap` event carrying `outcome` → STOP. Ask the user to run
  `/gm-fixgap`.
- Otherwise → proceed (evaluate is naturally re-invoked after each verify pass).

## Resolve `godot` binary

Read `godot_path` from `.claude/godotmaker.yaml` and substitute it
verbatim for `<godot_path>` in every `godot --headless …` command
below. The path was validated at publish time and is the source of
truth for which Godot binary this project uses.

If `.claude/godotmaker.yaml` is missing the `godot_path` field, fall
back to plain `godot` (PATH lookup). If THAT also fails, STOP and tell
the user `Godot binary not configured — re-run tools/publish.py to set
godot_path in .claude/godotmaker.yaml`. Do NOT spelunk through PATH
directories or guess install locations.

## Evaluation Process

### Phase 1 — Understand Requirements

Read in order:

1. `PLAN.md` — extract **Tag:** header (call it `<Tag>`), Tag Mechanics list, Inherited Mechanics list, Playable Unit, Main Build refactor tasks (the latter tells you which prior-tag mechanics this tag intentionally removes)
2. `GDD.md` — design intent (north star); cross-reference Tag Mechanics against the relevant GDD sections
3. `STRUCTURE.md` — current tag's ECS architecture
4. `SCENES.md` — current tag's scenes
5. `ASSETS.md` — cross-tag asset manifest
6. `DESIGN.md` — the project's visual contract: Visual Identity, the nine
   Image Style dimensions, UI Visual Language, and the Do / Don't lists. This
   is the sole authority for every visual judgement in Phase 3. Read only this
   file for visual rules. A migrated project may still carry a legacy visual
   seed file beside it; that file is history and must never be opened, quoted,
   or used to fill a gap — an unwritten `DESIGN.md` section simply has no rules
   to check.
7. `ROADMAP.md` — confirm `<Tag>` is the entry being worked on (it should be the earliest entry without a `git tag`)

Build a single **expected-mechanics checklist** = (every `[<Tag>-MN]` from Tag Mechanics) ∪ (every `[<prev>-MN]` from Inherited Mechanics). This is the union of mechanics the game must currently support. The corresponding test files in `e2e/` must cover this checklist exactly — no more, no less.

Build a **playable-unit checklist** from PLAN.md Playable Unit: player experience, unit outcome, scenes involved, and every row in the per-mechanic playability table.

Key `playable_unit.rows` by mechanic id, for example `v0.1.0-M1`.

### Phase 2 — Maintain the e2e/ suite

E2E tests live in a flat `e2e/` directory (no per-tag subdirectories). Each test file is named after the mechanic id it covers, e.g. `e2e/test_v0.1.0_M1_wasd_movement.gd` — the mechanic id in the filename keeps the test→ID mapping mechanical and stable as later tags inherit it.

1. Read `.claude/skills/godot-e2e/SKILL.md` for the API.
2. Confirm `e2e/conftest.py` exists at the e2e root (created by gm-scaffold).
3. **Add tests for new Tag Mechanics:** for each `[<Tag>-MN]` in PLAN.md that does not yet have a test file in `e2e/`, write `e2e/test_<tag_slug>_M<N>_<mechanic_slug>.gd` (or `.py`). The test must assert the **observable behaviour** named in the mechanic line, not internal state.
4. **Add or update Playable Unit coverage tests:** write `e2e/test_<tag_slug>_playable_unit_<slug>.gd` (or `.py`) files until every Playable Unit table row is covered. Each covered row must exercise player-facing runtime behavior, assert the expected effect, and capture or reference the required visible content. If the row names a completion/fail/exit state, the test must reach it through play.
5. **Verify Inherited Mechanic tests still exist:** for each `[<prev>-MN]` in PLAN.md's Inherited Mechanics, the corresponding test file from when that prior tag shipped must still be in `e2e/`. If a file is missing (e.g. accidentally deleted), restore it by reading `docs/tags/<prev>/PLAN.md` and re-implementing the test.
6. **Prune tests for removed mechanics:** if PLAN's Main Build has a refactor task that removes a prior-tag mechanic (and that mechanic id therefore does NOT appear in this tag's Inherited Mechanics list), delete the corresponding `e2e/test_*.gd` file. Removal is intentional, refactor task is the audit trail.
7. **Add scene-transition tests** for new scenes added in this tag.
8. Run the full suite: `godot-e2e e2e/ -v`
9. Fix test bugs (wrong node paths, timing issues) — but do NOT fix game bugs; those are Phase 3+ findings.

**E2E repair boundary:**
- E2E tests verify observable gameplay requirements. Do NOT prescribe fixgap's
  implementation strategy.
- When a state cannot be reached reliably in E2E, record the observed gap and
  request the deterministic test interface needed to exercise it.
- Test interfaces include `simulate_*` methods, scene setup helpers, fixed
  seeds, public state setup, or debug-safe setup paths that call real runtime
  code.
- Do NOT ask fixgap to change normal gameplay behavior, balance, progression,
  content, or timing only to satisfy a test assertion.
- If normal gameplay itself violates GDD/PLAN, cite the design source and
  record the gameplay failure.

When requesting a test interface, write both evidence entries:

- `observed_gap: <observable state or behavior not proven by E2E>`
- `requested_test_interface: <bounded setup or simulate interface needed>`

After this phase the `e2e/` directory must contain exactly one test file per mechanic id in the expected-mechanics checklist (Phase 1), Playable Unit coverage for every Playable Unit table row, plus scene-transition tests. Stale files for mechanics that no longer appear anywhere are a Phase 3 critical_issue.

Before completing `/gm-evaluate`, write one `playable_unit.rows` entry for
every PLAN Playable Unit row. Each entry must include `result`, `test`, and
non-empty `evidence`; the referenced test file must exist. For approve, every
row must be `pass`.

### Phase 3 — Mandatory Checks

All of these must pass for `result == "approve"`. Failure of any is a `critical_issue`.

**Playable closed loop (composite hard gate):**
1. **Builds clean:** `"<godot_path>" --headless --quit 2>&1` — zero ERROR lines.
2. **Boots into main scene:** `project.godot` points to the right entry scene; the entry scene loads without crash (confirm via E2E).
3. **Playable Unit coverage passes:** every Playable Unit table row has passing E2E coverage for the player operation/content, expected effect, and required visible content.
4. **Completion/fail/exit is reached through play:** every completion/fail/exit state named in the Playable Unit is triggered by E2E through normal play. Static code evidence is not enough.

**Mechanics gate (covers both new and inherited):**
5. Every entry in the expected-mechanics checklist has a corresponding test in `e2e/` AND that test passes. Each PASS/FAIL recorded against the mechanic id. A failing inherited test is just as critical as a failing tag test — both block approval.
6. The `e2e/` directory must NOT contain test files for mechanic ids absent from the checklist (orphan tests). Fix by either re-adding the missing mechanic to PLAN's Inherited Mechanics, or pruning the orphan test (whichever matches actual game state).

**Visual cross-check (per scene listed in SCENES.md):**
7. Capture screenshots under `e2e/screenshots/`. Use `game.screenshot("e2e/screenshots/scene_{name}.png")` for static scenes. For scenes with motion/animation, capture a frame sequence per `.claude/skills/screenshot/SKILL.md` § "Frame Sequence for VQA Dynamic Mode". Treat `e2e/screenshots/` as latest-run output only.
8. Inspect the captured screenshots by dispatching a subagent to run the
   `visual-qa` skill in Question mode. Do not compare screenshots against
   `references/scene_{name}.png`.

   **Visual binding preflight.** Before calling visual-qa, check the scene's
   `Asset bindings` rows. Each non-`procedural` / non-`UI text` /
   non-`not required this tag` binding must have:
   - a concrete `asset_name / path` value;
   - a matching ASSETS.md Asset Table row;
   - a matching ASSETS.md Visual Asset Contract row;
   - a non-empty Runtime Size;
   - an existing file when the row status means the asset should be on disk.

   If the scene has no `Asset bindings` section or ASSETS.md has no Visual
   Asset Contract section, record `missing visual contract for <scene>` in
   `major_issues`, then continue VQA with the scene Acceptance criteria and
   mechanic fallback context. If the sections exist but a current-tag binding is
   incomplete, record a `critical_issue`, set this scene's
   `visual_checks.<scene>.result` to `"fail"`, note the exact missing binding in
   `visual_checks.<scene>.notes`, and skip visual-qa for that scene.

   For `not required this tag`, require a deferral reason in the Visual Contract
   or Readability Requirement text. Missing deferral reasons are incomplete
   bindings.

   **Question construction.** A scene is judged on two independent things: the
   content it must show, and the design rules it must obey.

   *Content requirements.* Pull the `Acceptance criteria` block from
   SCENES.md for this scene. Add the scene's `Asset bindings` rows and matching
   ASSETS.md Visual Asset Contract rows. If the block is absent, fall back to
   the mechanic ids from PLAN.md Tag Mechanics + Inherited Mechanics that this
   scene exercises, each with its one-line description. These cover the
   required visible content, readability, layout, and motion/animation
   requirements. For deterministic setup screenshots, add
   `Visible state only; do not infer prior play history.`.

   *Design rules.* Classify what the capture shows, then build the rule list
   with the tool — do not summarise `DESIGN.md` yourself:

   | Subject class | Use when the capture shows |
   |---|---|
   | `character` | a character or creature on its own (a generated sheet, a portrait) |
   | `environment` | a staged space with no UI: background, tileset, props, platforms |
   | `ui` | UI surfaces only: HUD, menu, card face, inventory panel |
   | `mixed` | a played scene with both world content and UI — most gameplay screenshots |

   ```bash
   python tools/design_rules.py build-request --design DESIGN.md \
     --subject {character|environment|ui|mixed} --name scene_{name} --kind scene \
     --capture e2e/screenshots/scene_{name}.png \
     --requirement "{one acceptance criterion or contract row}" \
     --reference references/scene_{name}.png \
     --output .godotmaker/design-checks/scene_{name}-request.json
   ```

   Repeat `--capture` for a frame sequence and `--requirement` per criterion.
   Every capture must already exist under the project root — `build-request`
   fails if one does not, which means the screenshot step did not produce it.
   Fix the capture; never grade a missing screenshot as a backend error.
   The tool selects the rules that apply to that subject class — a UI-only
   capture additionally carries every UI Visual Language rule, while rules that
   cannot be observed in it (lighting and shadow, space and depth) come back
   `not_applicable` with a reason rather than being dropped. Render the
   question text with `--question` and pass it verbatim as `--question` to
   visual-qa.

   `--reference` is provenance context only. Do not ask whether the capture
   resembles the reference: a different composition in the same visual language
   is not a defect, and copying the reference's composition does not excuse a
   rule violation. When a reference and `DESIGN.md` disagree, `DESIGN.md` wins
   and the disagreement goes in `visual_checks.<scene>.notes`.

   **Grading design rule findings.** Transcribe the `Design Rule Findings`
   block visual-qa returned into
   `.godotmaker/design-checks/scene_{name}-findings.json` — one object per
   rule, verbatim, inventing nothing:

   ```json
   [
     {
       "rule_id": "dont.r1",
       "verdict": "pass | fail | uncertain | not_applicable",
       "evidence": "<the backend's observation, copied>",
       "confidence": "high | medium | low",
       "evidence_conflict": false,
       "captures": ["e2e/screenshots/scene_<name>.png"]
     }
   ]
   ```

   Then feed it back through the tool. Never derive severity yourself:

   ```bash
   python tools/design_rules.py grade \
     --request .godotmaker/design-checks/scene_{name}-request.json \
     --findings .godotmaker/design-checks/scene_{name}-findings.json \
     --output .godotmaker/design-checks/scene_{name}-graded.json
   ```

   If the visual-qa invocation errored or its backend was unavailable, run the
   same command with `--backend-error "<message>"` instead of `--findings`: an
   unchecked contract must not read as a checked one.

   The grader rejects an incomplete answer rather than filling the hole: a
   missing rule, an invented `rule_id`, a `fail` or `uncertain` with no
   evidence, or an answer on a rule the request marked N/A all fail the
   command. Re-call visual-qa for the rules it skipped instead of writing
   them yourself.

   The grader applies one policy, and it is the whole blocking rule:

   - a high-confidence failure of a `Don't` entry, a literal `MUST` /
     `MUST NOT` rule, or any other rule the author marked required →
     `disposition: blocking`, `severity: blocker`;
   - an ordinary `Do` entry or an ordinary dimension bullet that the capture
     deviates from → `disposition: non_blocking`. It is reported, never
     promoted to a blocker;
   - `uncertain`, conflicting evidence, or a low/medium-confidence suspected
     violation of a required rule → `disposition: human_review`. Never convert
     one of these into a PASS or into a hard fail on your own.

   Copy the graded `findings[]` into `visual_checks.<scene>.design_rules`, and
   set `visual_checks.<scene>.design_rule_result` and
   `human_review_required` from the graded output. Route the graded
   `critical_issues` / `major_issues` / `minor_issues` into the top-level lists
   of the same name.

   **Design rule findings never override the deterministic checks below.** The
   binding preflight, atlas misuse check, build, mechanics, and E2E gates own
   their own verdicts; a design rule cannot clear a failing one, and a passing
   one cannot clear a blocking design rule violation.

   **Atlas misuse check.** When a scene's `Asset bindings` reference a
   `region_atlas` (or a single element sourced from a `grid_sheet`), add to the
   question whether each element shows only its intended region/sprite and not
   the whole atlas or sheet. A visible full atlas or sheet where a single
   button, icon, prop, or FX sprite is expected is a `critical_issue`; set this
   scene's `visual_checks.<scene>.result` to `"fail"` and note the misused
   binding in `visual_checks.<scene>.notes`.

   **VQA log path.** Ask `visual-qa` to write its debug log to `e2e/screenshots/vqa.log`.

   `{design_rule_question}` below is the exact text
   `python tools/design_rules.py build-request ... --question` printed. Pass it
   verbatim; do not paraphrase it or trim the rule list.

   ```
   # Static scene — dispatch a subagent to run visual-qa with:
   --question "{design_rule_question} Also report a separate `### Content Verdict` covering ONLY the content requirements below, never the design rules: does this screenshot satisfy the scene contract? Goal: {scene goal from SCENES.md}. Requirements: {SCENES.md Asset bindings + matching ASSETS.md Visual Asset Contract rows}. Verify: {acceptance criteria block, or mechanic-id list fallback}." e2e/screenshots/scene_{name}.png --log e2e/screenshots/vqa.log

   # Dynamic scene (frame sequence in per-scene subdir) — dispatch a subagent to run visual-qa with:
   --question "{design_rule_question} Also report a separate `### Content Verdict` covering ONLY the content requirements below, never the design rules: does this frame sequence satisfy the scene contract? Goal: ... Requirements: {SCENES.md Asset bindings + matching ASSETS.md Visual Asset Contract rows}. Verify: required content remains visible, motion is fluid, no stuck entities, and animation matches movement." e2e/screenshots/scene_{name}/frame_*.png --log e2e/screenshots/vqa.log
   ```

   **Audit trail.** Record every visual-qa call (verdict + context + mode + files + log path + output digest) in `visual_checks.{scene_name}.vqa_calls[]` (schema below). Also record the screenshot/frame paths used in `visual_checks.{scene_name}.captures[]`, and the graded per-rule findings in `visual_checks.{scene_name}.design_rules[]`. Keep the request, raw findings, and graded output under `.godotmaker/design-checks/` so the chain from rule text to verdict stays inspectable. If you override a recorded verdict for the final `result` — for instance you read the PNGs yourself and disagree — write the reason and what you saw into `visual_checks.{scene_name}.notes`. Either way, `result` reflects the chain transparently.

   A design rule finding may only be re-dispositioned through the graded
   output's `override` field, which requires `by: human` and a reason. You
   cannot silently promote a `non_blocking` finding to a blocker, nor resolve a
   `human_review` finding yourself — report it and let the user decide.

   **Real invocation required.** Every `vqa_calls` entry, every `vqa.log` line, and every `design_rules[]` verdict must come from a visual-qa invocation — do not author them directly. If the invocation errors or its backend is unavailable, grade it with `--backend-error`, record a `critical_issue`, and set `result: reject`.

   If a `fail` looks wrong, prefer re-calling visual-qa with refined context before overriding by hand. If the final visual-qa output marks an issue as style-only or non-blocking, do not promote it to `critical_issue`; record it in `visual_checks.{scene_name}.notes` or `minor_issues`.

   - Verdict mapping runs on the visual-qa `### Content Verdict`, **never on
     the overall `### Verdict`**: `fail` → critical_issue; `warning` →
     major_issue; `pass` → recorded under `visual_checks`. The overall verdict
     combines content and design rules, so mapping it here would promote an
     ordinary `Do` entry or dimension deviation into a blocker — exactly what
     the grader classifies as `non_blocking`. Record the overall verdict in
     `vqa_calls[].verdict` for the audit and gate on the content one.
   - If the backend omitted `### Content Verdict` while the question did state
     content requirements, do not fall back to the overall verdict: re-call
     visual-qa for the content answer. Guessing which half a `fail` came from
     is how a non-blocking finding becomes a blocker.
   - Design rule blocking comes from the graded `disposition` alone. The
     scene's `result` is the worse of the content verdict and the graded
     `design_rule_result`. A `blocking` design rule finding forces `fail`; a
     `human_review` or high-confidence `non_blocking` finding forces at worst
     `warning`, which is a major_issue and does not block the tag.
   - Backend follows `vqa_model` / `vqa_fallback_model` in `.godotmaker/config.yaml`.

For each check, record: **PASS** or **FAIL** with evidence (E2E output, screenshot path, error message).

### Phase 4 — Gameplay Reasoning

Pick the experience categories that fit this game (e.g. readability, control feel, attack feedback, fresh-player guidance, character framing, pacing — whatever this game's design hinges on) and write your assessment for each into `phase4_review`. An empty `phase4_review` is not acceptable.

Each entry: `{ "category": "<name>", "verdict": "ok" | "issue: <one-line description>" }`. Mirror each `issue:` verdict into `gameplay_issues` as a one-line entry.

### Phase 5 — Final Assessment (Pass/Fail)

This is NOT a score. The tag either ships or it doesn't.

**Pass criteria — ALL must be true:**
- All Phase 3 mandatory checks pass (playable closed loop + mechanics gate + visual checks)
- No critical_issues unaddressed
- Every Playable Unit table row has passing E2E coverage, and each named completion/fail/exit state is reached through play
- Every mechanic in the expected-mechanics checklist has a passing test in `e2e/`
- No orphan test files in `e2e/` (every test maps to a mechanic still in PLAN)

**If ANY criteria fails → REJECT.** List every failing item with evidence; the gm-fixgap loop will pick them up.

**If ALL criteria pass → APPROVE.**

## Output

Write evaluation results to `.godotmaker/evaluation.json`:

```json
{
  "tag": "<Tag>",
  "result": "approve | reject",
  "playable_closed_loop": {
    "builds_clean": true,
    "boots_main_scene": true,
    "playable_unit_coverage": true,
    "completion_fail_or_exit_reached": true
  },
  "playable_unit": {
    "result": "pass | fail",
    "rows": {
      "<mechanic_id_or_row_name>": {
        "result": "pass | fail",
        "test": "e2e/test_<tag_slug>_playable_unit_<slug>.gd",
        "evidence": [
          "<runtime behavior, assertion, screenshot, video frame, or log path>",
          "observed_gap: <observable state or behavior not proven by E2E>",
          "requested_test_interface: <bounded setup or simulate interface needed>"
        ]
      }
    }
  },
  "tag_mechanics": {
    "<Tag>-M1": "pass",
    "<Tag>-M2": "fail"
  },
  "inherited_mechanics": {
    "v0.1.0-M1": "pass",
    "v0.1.0-M2": "pass"
  },
  "visual_checks": {
    "<scene_name>": {
      "screenshot": "e2e/screenshots/scene_<name>.png",
      "captures": ["e2e/screenshots/scene_<name>.png"],
      "vqa_log": "e2e/screenshots/vqa.log",
      "result": "pass | fail | warning",
      "design_rule_result": "pass | fail | warning",
      "human_review_required": false,
      "notes": "",
      "design_rules": [
        {
          "rule_id": "dont.r1",
          "group": "dont",
          "source": "DESIGN.md > Don't",
          "rule_text": "<the rule verbatim from DESIGN.md>",
          "requirement": "required | normal",
          "verdict": "pass | fail | uncertain | not_applicable",
          "evidence": "<what is observable in the capture>",
          "confidence": "high | medium | low",
          "evidence_conflict": false,
          "disposition": "pass | blocking | non_blocking | human_review | not_applicable",
          "severity": "blocker | major | minor | none",
          "captures": ["e2e/screenshots/scene_<name>.png"],
          "na_reason": "<required when verdict is not_applicable>"
        }
      ],
      "vqa_calls": [
        {
          "ts": "<UTC ISO 8601>",
          "mode": "question",
          "backend": "native | codex | gemini | openai",
          "model": "<vqa_model or fallback selector used>",
          "files": ["e2e/screenshots/scene_<name>.png"],
          "log": "e2e/screenshots/vqa.log",
          "context": "Goal: ... Requirements: ... Verify: ...",
          "verdict": "pass | fail | warning",
          "content_verdict": "pass | fail | warning | n/a",
          "output_summary": "<first line or 1-sentence digest of the visual-qa response>"
        }
      ]
    }
  },
  "phase4_review": [
    {"category": "scene_readability", "verdict": "ok"},
    {"category": "control_feel", "verdict": "issue: jump feels sluggish — coyote-time window too short"}
  ],
  "e2e_tests": {"total": 0, "passed": 0, "failed": 0},
  "orphan_tests": [],
  "gameplay_issues": ["..."],
  "critical_issues": ["must fix items"],
  "major_issues": ["should fix items"],
  "minor_issues": ["nice to have items"]
}
```

After writing evaluation.json, from the project root run `python tools/append_stage_event.py evaluate --tag=<Tag>` to append a `{"role": "evaluate", "ts": "<server-generated UTC>", "tag": "<Tag>"}` line to `.godotmaker/stage.jsonl`. Do NOT hand-write the JSON or the timestamp — the helper exists so the timestamp comes from the system clock, not your own output.

Do not manually create `.godotmaker/evaluation-runs/`; `append_stage_event.py` owns the evaluate-run archive.

Then: `git add -A && git commit -m "chore(evaluate): <Tag>"`.

## When Done

- If `result` is `"reject"` → inform user: `Evaluation rejected for <Tag>. Recommended next: /gm-fixgap`
- If `result` is `"approve"` → inform user: `Evaluation approved for <Tag>. Recommended next: /gm-accept`
