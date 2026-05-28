# The 9 pipeline roles + 1 diagnostic role

Each role is a slash command you type in Claude Code. The 9 pipeline roles run in order — you will be told if you skipped a prerequisite. The 10th role, `/gm-rescue`, lives outside the main pipeline and is invoked only when something has stuck.

The pipeline runs **per tag** (SemVer: v0.1.0, v0.2.0, …). One full pass through `/gm-gdd → /gm-finalize` ships exactly one tag. `/gm-scaffold` runs once at the very start of a project. After `/gm-finalize` closes a tag, you can start the next one with another `/gm-gdd`.

`ROADMAP.md` lists the planned tags; the earliest entry that does not yet have a `git tag` is the **current tag**.

---

## `/gm-scaffold`

**What it does:** Creates an empty Godot project with the right folder structure, installs the required addons (`gecs` for ECS support, `gdUnit4` for testing), and makes the first git commit.

**When to run it:** Once, before anything else. The project directory must exist but be empty (or have only a `.git` folder).

**What happens behind the scenes:**
- Writes `project.godot`, `addons/`, `src/`, `scenes/`, `assets/`, `e2e/`, `test/`
- Installs and configures `gecs` and `gdUnit4`
- Creates `e2e/conftest.py` (the test harness entry point)

**What you get:** A clean, runnable Godot project with no game logic yet.

**Things to know:** This command runs only once per project. Running it a second time in the same project stops early with an explanation.

---

## `/gm-gdd`

**What it does:** Plans the **current tag**. Runs in two modes depending on whether `ROADMAP.md` already exists:

- **Initial mode** (no `ROADMAP.md` yet): full Socratic interview about the whole game → produces `GDD.md` → derives `ROADMAP.md` (split into SemVer-tagged release tags) → asks you to confirm the roadmap → generates v0.1.0's working docs.
- **Subsequent mode** (`ROADMAP.md` exists): focuses on the current tag's roadmap entry → asks if you want to keep, adjust, or rewrite the design → optionally updates `GDD.md` (old features marked `(superseded by …)` rather than deleted) and `ROADMAP.md` → generates the current tag's working docs (refactor tasks for prior-tag code if design contradicts what shipped).

**When to run it:** After `/gm-scaffold` (first tag), or after `/gm-finalize` (each subsequent tag).

**What you get:**
- Cross-tag (root, accumulating): `GDD.md`, `ROADMAP.md`, plus new rows appended to `ASSETS.md`
- Current tag (root, overwritten this round): `PLAN.md` (with `**Tag:**` header, Tag Mechanics list, Inherited Mechanics list), `STRUCTURE.md`, `SCENES.md`, `TOC.md`

**Things to know:** Be specific in the interview — "a top-down zombie shooter with wave-based spawning and a high-score screen" is much more useful than "a zombie game". The roadmap confirmation gate is mandatory; you cannot proceed to artifact generation until you confirm. You can edit any of the documents before running `/gm-asset`.

---

## `/gm-asset`

**What it does:** Fills in the new assets this tag introduces (working only on rows the current tag added; prior-tag rows are immutable here).

**When to run it:** After `/gm-gdd`, before `/gm-build`. Re-runnable any time during the tag if you add new art.

**What happens behind the scenes:**
- Reads the current tag's MISSING rows from `ASSETS.md`
- For assets you have already provided: dispatches an Analyst helper to inspect your image files and record what they contain
- For assets that are still missing: generates them via an image generation API (Gemini or xAI, depending on your configuration)
- For each entry in `SCENES.md`: generates a target reference image at `references/scene_<name>.png` from the scene description, art direction, and your provided art style
- Updates `ASSETS.md` with the actual file paths and final status

**What you get:** Art files in `assets/`, scene reference images in `references/`, and resolved status on this tag's `ASSETS.md` rows. The scene references become the visual contract that `/gm-evaluate` later compares running screenshots against.

**Things to know:** If a previous tag's asset is broken, raise it as a fix task in `/gm-fixgap`.

---

## `/gm-build`

**What it does:** Implements the **current tag's** scope — all the GDScript code, scenes, and unit tests for this tag — by coordinating a team of specialised helpers.

**When to run it:** After `/gm-asset`. Requires a completed `/gm-gdd` for the current tag.

**What happens behind the scenes:**
- On resume, reads `.godotmaker/verify_report.json` if a fresh failure report exists from the previous `/gm-verify`, and translates each per-check failure into a `pending` task in the current tag's `PLAN.md` before continuing
- Reads the current tag's `PLAN.md` to find pending tasks, starting with the riskiest ones
- Dispatches Workers (up to 3 in parallel) — each Worker implements one game system and its unit tests, then reports back
- Once every task in `PLAN.md` is `completed`, dispatches a Verifier (compiles headlessly, runs unit tests) and then a Reviewer (domain knowledge about Godot pitfalls — physics, UI, animation, etc.) — one verify+review pass per cycle iteration, not per worker
- For each reviewer finding the main agent picks one of three options: ACCEPT (add a new fix task to `PLAN.md`), REJECT (the finding is wrong — record in `MEMORY.md`'s **Reviewer Triage Log**), or SKIP (the finding is real but not worth fixing now — same MEMORY.md section). Defaults: critical/major → ACCEPT; minor → SKIP. REJECT/SKIP for critical/major requires a mandatory citation (gotcha entry, API doc, prior decision, or task ID)
- If any findings were ACCEPTED, the cycle loops back to dispatching Workers
- The build ends only when every task in `PLAN.md` is `verified` and the last review round added zero ACCEPTED tasks

**What you get:** Game code in `src/`, scenes in `scenes/`, unit tests in `test/` — all scoped to this tag's additions / refactors.

**Things to know:** You cannot write game code yourself while in this step — the permission system blocks it. The main agent coordinates; Workers do the actual writing. Workers may touch files outside the current tag's scope only when `PLAN.md` has an explicit refactor task naming those files; "cleanup detours" are not allowed. If the same task fails three times, the build stops and asks you what to do.

---

## `/gm-verify`

**What it does:** Runs a fast mechanical check of the whole project — compile, unit tests, lint, project completeness. Tag-agnostic; runs against current state regardless of which tag you're on.

**When to run it:** After `/gm-build`, and again after each `/gm-fixgap`.

**What happens behind the scenes:**
- Runs the Godot headless build to check for compile errors
- Runs all unit tests in `test/` via `gdUnit4`
- Runs the static project check via `tools/check_project.py` (build/ecs/tests/plan/mcp; e2e gating is the Evaluator's job)
- Writes the structured verdict to `.godotmaker/verify_report.json` (every run, pass or fail)

**What you get:** Two outputs — a chat-readable verification report you can scan, and `.godotmaker/verify_report.json` with the same information in a structured form. On success, `/gm-verify` also appends a `verify` event to `.godotmaker/stage.jsonl`.

**Things to know:** `verify_report.json` is the protocol-level feedback channel for the next role in the loop — `/gm-build` and `/gm-fixgap` read it to translate failures into pending tasks instead of retrying blindly. Each check's `result` is one of `pass | warn | fail | error`: `fail` = project code has problems (fix the code), `error` = the verification tool itself crashed and the fix is a config change documented in `tooling_notes` (don't delete project code). Schema and consumer rules live in `gm-verify/SKILL.md`. `/gm-verify` does NOT enforce tag-specific E2E or regression — that's `/gm-evaluate`'s job. If verify fails, go back to `/gm-build` (mid-build) or `/gm-fixgap` (post-evaluation) — both pick up the report automatically.

---

## `/gm-evaluate`

**What it does:** Independently assesses whether the **current tag** delivers what its `PLAN.md` claimed and whether every still-supported mechanic from prior tags still works.

**When to run it:** After `/gm-verify` passes.

**What happens behind the scenes:**
- Reads the current tag's `PLAN.md` Tag Mechanics + Inherited Mechanics — with no memory of the build process
- Maintains a single `e2e/` directory that always reflects the current game: writes new tests for this tag's Tag Mechanics, verifies inherited tests still exist, and prunes tests for mechanics PLAN's Main Build refactor tasks deliberately removed
- Enforces the **playable-closed-loop hard gate**: headless boot + at least one mechanic E2E + at least one of {death, win, exit} ending exists
- Runs the full `e2e/` suite — every test for every still-supported mechanic. A failing inherited mechanic is just as critical as a failing new one
- Takes screenshots of each scene and compares them against reference images using a visual quality check
- Produces a final verdict: approve or reject, with a list of specific problems if rejected

**What you get:** `.godotmaker/evaluation.json` (the full verdict, with per-mechanic PASS/FAIL records), latest screenshots in `e2e/screenshots/`, and archived evaluate-run evidence under `.godotmaker/evaluation-runs/`.

**Things to know:** The evaluator cannot write game code or touch `src/` — it is strictly read-only on game files. A rejection is not a failure; it is information. The problem list feeds directly into `/gm-fixgap`.

---

## `/gm-fixgap`

**What it does:** Reads the evaluation's problem list and dispatches workers to fix each issue (within the current tag's scope).

**When to run it:** After `/gm-evaluate` rejects the build.

**What happens behind the scenes:**
- Reads `.godotmaker/evaluation.json` for product-layer issues and, on resume, `.godotmaker/verify_report.json` for any mechanical failures from the latest verify pass
- Generates or merges `GAP.md` — a prioritised task list that lists verify-source mechanical fixes first, then evaluation-source product fixes, within shared `C` / `J` / `G` severity prefixes
- Dispatches Workers to address each critical and major issue, with the same Worker → Verifier → Reviewer cycle as `/gm-build`
- Archives the current `GAP.md` to `.godotmaker/gaps/<n>/` so every iteration is preserved

**What you get:** Updated game code, with `GAP.md` moved to the archive.

**Things to know:** Tag-scope discipline applies here too — fixes touching prior-tag code require an explicit GAP item naming those files. After `/gm-fixgap` finishes, run `/gm-verify` and then `/gm-evaluate` again. The loop continues until `/gm-evaluate` approves; if you see no progress after several rounds, run `/gm-rescue` to diagnose whether godotmaker itself is the blockage.

---

## `/gm-accept`

**What it does:** Presents the approved tag to you and records your decision.

**When to run it:** After `/gm-evaluate` approves.

**What happens behind the scenes:**
- Shows you a per-tag summary: tag mechanics delivered, inherited mechanics still passing, screenshots, known limitations, what's left in the roadmap
- Asks: accept (proceed to `/gm-finalize`), reject (go back to `/gm-fixgap`), or stop
- Records your answer in `.godotmaker/stage.jsonl`

**What you get:** A recorded acceptance event for this tag, or a clear instruction to loop back.

**Things to know:** Accepting here means **this tag is ready to seal** — not that the whole game is done. You can stop the project at any tag boundary; the user-decision authority is yours, not the tooling's.

---

## `/gm-finalize`

**What it does:** Seals the **current tag** — archives the working docs, writes a per-tag changelog, runs `git tag <Tag>`, and resets per-tag runtime state for the next round.

**When to run it:** After `/gm-accept` records an acceptance.

**What happens behind the scenes:**
- Verifies the project still builds clean and `evaluation.json` says `approve`
- Reconciles `PLAN.md`, `STRUCTURE.md`, and scene docs against the final code so archived names match the systems and components that actually shipped
- Copies the current `GDD.md`/`PLAN.md`/`STRUCTURE.md`/`SCENES.md`/`MEMORY.md` (full snapshots) and `evaluation.json` into `docs/tags/<Tag>/`
- Generates `docs/tags/<Tag>/CHANGELOG.md` summarising delivered mechanics, added systems, and any cross-tag refactors
- Runs `git tag <Tag>` locally (does not push)
- Truncates `.godotmaker/stage.jsonl` and resets per-tag runtime state so the next `/gm-gdd` starts on a clean slate

**What you get:** An immutable archive at `docs/tags/<Tag>/`, a local git tag, and a clean per-tag state for the next round.

**Things to know:** This skill does NOT package a release zip; release packaging is a separate concern (a future skill). `/gm-finalize` does not push the git tag — that decision is yours.

---

## `/gm-rescue` (out-of-pipeline)

**What it does:** Diagnoses whether the pipeline is stuck because of a defect in godotmaker itself (hooks, skills, config, templates), or because of something outside godotmaker's responsibility (GDD self-contradiction, AI implementation difficulty, environment issues).

**When to run it:** Only when the pipeline is stuck — typically after several `/gm-fixgap` rounds fail to converge, or when you suspect a framework bug rather than a game-code bug.

**What happens behind the scenes:**
- Reads the runtime artifacts (`.godotmaker/current_role`, `stage.jsonl`, `evaluation.json`, recent `traces/`, `metrics.jsonl`) and the per-tag working docs (`PLAN.md`, `GAP.md` if present, `MEMORY.md`)
- Walks the godotmaker layers (hooks → SKILL.md → config → templates → shared refs → tools) looking for a defect that matches the symptom
- Outputs a diagnosis to chat — never modifies game code, never writes files (the only mutations are setting `.godotmaker/current_role` to `rescue` and appending one rescue event to `stage.jsonl`)
- If a godotmaker defect is found: drafts a GitHub issue text you can review and post upstream
- If not a godotmaker defect: explicitly tells you so, and points at the likely cause (GDD logic, missing assets, AI capability ceiling, etc.)

**What you get:** A chat message with the diagnosis. No file changes anywhere.

**Things to know:** Privacy — the issue draft excludes absolute project paths, your project's source code, and your GDD content by default. You decide whether to redact further before posting. `/gm-rescue` does not loop or retry; it diagnoses once and reports.

---

## What is a tag?

One tag = one round of `/gm-gdd` → `/gm-asset` → `/gm-build` → `/gm-verify` → `/gm-evaluate` → (fixgap loop) → `/gm-accept` → `/gm-finalize`.

`ROADMAP.md` lists the planned tags. The first tag (always `v0.1.0`) delivers the playable closed loop — the smallest playable game. Each later tag adds a feature set or major revision. This lets you grow the game incrementally and gives you a chance to stop, ship, or pivot at every tag boundary.

For a bird's-eye view of how the phases connect, see [how-it-works.md](how-it-works.md).
