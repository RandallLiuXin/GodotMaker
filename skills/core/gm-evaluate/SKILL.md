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

**Permission:** You can write to `e2e/`, `.godotmaker/evaluation.json`, and append to `.godotmaker/stage.jsonl` (plus `.godotmaker/current_role` set during Session Setup). All other files are read-only.

## Resume Check

Read `.godotmaker/stage.jsonl` (treat as empty if missing) — each line is `{"role": X, "ts": Y}`.

- If **no event with `role == "verify"`** exists anywhere in the file → STOP. Tell user to run `/gm-verify` first.
- If `PLAN.md` is missing the `**Tag:**` header → STOP. Tell user the file is stale and to re-run `/gm-gdd` to regenerate it for the current tag.
- If the **last event** has `role == "evaluate"` AND `.godotmaker/evaluation.json` exists → STOP. Tell the user:
  > "Evaluate already ran at {timestamp} with no verify since. Recommended next: /gm-accept (if approved) or /gm-fixgap (if rejected).
  > If you need to redo this step or have other plans, just tell me."
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
6. `ROADMAP.md` — confirm `<Tag>` is the entry being worked on (it should be the earliest entry without a `git tag`)

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
8. Compare against the reference image in `references/scene_{name}.png` by dispatching a subagent to run the `visual-qa` skill.

   **Precondition — reference must exist.** Before calling visual-qa, confirm `references/scene_{name}.png` exists. If missing → record `critical_issue: "missing reference for scene_{name}"` and skip the visual-qa call for this scene. Do NOT degrade to Question mode against the screenshot alone.

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

   **Context construction.** Pull the `Acceptance criteria` block from SCENES.md for this scene; paste it verbatim into the `Verify:` field. Add the scene's `Asset bindings` rows and matching ASSETS.md Visual Asset Contract rows to `Requirements:`. If the block is absent, fall back to the mechanic ids from PLAN.md Tag Mechanics + Inherited Mechanics that this scene exercises, each with its one-line description. Never leave `Requirements:` or `Verify:` as a placeholder. For deterministic setup screenshots, add `Visible state only; do not infer prior play history.` to `Verify:`.

   **VQA log path.** Ask `visual-qa` to write its debug log to `e2e/screenshots/vqa.log`.

   ```
   # Static scene — dispatch a subagent to run visual-qa with:
   "Check references/scene_{name}.png against e2e/screenshots/scene_{name}.png --log e2e/screenshots/vqa.log — Goal: {scene goal from SCENES.md}, Requirements: {SCENES.md Asset bindings + matching ASSETS.md Visual Asset Contract rows}, Verify: {acceptance criteria block, or mechanic-id list fallback}."

   # Dynamic scene (frame sequence in per-scene subdir) — dispatch a subagent to run visual-qa with:
   "Check references/scene_{name}.png against e2e/screenshots/scene_{name}/frame_*.png --log e2e/screenshots/vqa.log — Goal: ..., Requirements: {SCENES.md Asset bindings + matching ASSETS.md Visual Asset Contract rows}, Verify: motion is fluid, no stuck entities, animation matches movement."
   ```

   **Audit trail.** Record every visual-qa call (verdict + context + mode + files + log path + output digest) in `visual_checks.{scene_name}.vqa_calls[]` (schema below). Also record the screenshot/frame paths used in `visual_checks.{scene_name}.captures[]`. If you override a recorded verdict for the final `result` — for instance you read the PNGs yourself and disagree — write the reason and what you saw into `visual_checks.{scene_name}.notes`. Either way, `result` reflects the chain transparently.

   **Real invocation required.** Every `vqa_calls` entry and every `vqa.log` line must come from a visual-qa invocation — do not author them directly. If the invocation errors or its backend is unavailable, record a `critical_issue` and set `result: reject`.

   If a `fail` looks wrong, prefer re-calling visual-qa with refined context before overriding by hand. If the final visual-qa output marks an issue as style-only or non-blocking, do not promote it to `critical_issue`; record it in `visual_checks.{scene_name}.notes` or `minor_issues`.

   - Verdict mapping (on the final recorded verdict): `fail` → critical_issue; `warning` → major_issue; `pass` → recorded under `visual_checks`.
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
        "evidence": ["<runtime behavior, assertion, screenshot, video frame, or log path>"]
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
      "reference": "references/scene_<name>.png",
      "vqa_log": "e2e/screenshots/vqa.log",
      "result": "pass | fail | warning",
      "notes": "",
      "vqa_calls": [
        {
          "ts": "<UTC ISO 8601>",
          "mode": "static | dynamic | question",
          "backend": "native | codex | gemini | openai",
          "model": "<vqa_model or fallback selector used>",
          "files": ["references/scene_<name>.png", "e2e/screenshots/scene_<name>.png"],
          "log": "e2e/screenshots/vqa.log",
          "context": "Goal: ... Requirements: ... Verify: ...",
          "verdict": "pass | fail | warning",
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
