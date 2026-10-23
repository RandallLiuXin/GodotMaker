# Writing a Skill

Skills are the instruction bundles that tell the selected coding agent what to do at each step of the pipeline. A skill is a folder containing a `SKILL.md` prompt, optional `references/` documents, and optional supporting files. When `publish.py` runs, every skill is copied flat into the selected agent's project-local skill folder (`.claude/skills/` for Claude Code or `.agents/skills/` for Codex).

## What kind of skill am I writing?

GodotMaker has three skill layers, each living in a different folder:

| Layer | Folder | Invoked by |
|-------|--------|-----------|
| **Role skill** | `skills/core/gm-*/` | `godotmaker-cli` or a manual `/gm-build`, `/gm-verify`, etc. |
| **Supporting skill** | `skills/core/<name>/` | Another skill loading it as a reference doc |
| **Reviewer skill** | `skills/reviewer/<name>/` | The reviewer sub-agent dispatched by `gm-build` / `gm-fixgap` |

Decision tree:
- Adding a new `/gm-*` command that owns a pipeline phase → **role skill**
- Adding domain knowledge that multiple existing skills need to reference → **supporting skill** (and likely a candidate for `_shared/` if two or more skills will use it)
- Adding checks for a new Godot subsystem (e.g. shaders, navigation) → **reviewer skill**

---

## Skill structure

Every skill directory needs at minimum one file:

```
skills/core/my-skill/
└── SKILL.md            Required. The prompt Claude reads.

Optional:
├── references/         Supporting docs loaded by the SKILL.md prompt.
└── assets/             Any static files the skill needs.
```

### SKILL.md front-matter

Start every `SKILL.md` with a YAML front-matter block:

```yaml
---
name: my-skill
description: |
  One paragraph explaining what this skill does and when Claude should use it.
  Be concrete: "Use when..." and "Does NOT handle..." help with matching.
disable-model-invocation: true
---
```

The `name` field is the slash command identifier. The `description` field is what Claude Code uses to match a user request to the right skill. The `disable-model-invocation: true` line is **required for role skills** — it prevents the skill from being invoked implicitly by the model; it must be called explicitly via the slash command.

A real example (from `skills/core/gm-build/SKILL.md`):

```yaml
---
name: gm-build
description: |
  Implement game systems via worker dispatch. Covers risk-first then main implementation.
  Dispatches workers until PLAN is clean, then runs one verify+review pass; loops until convergence.
  Explicit invocation only — use /gm-build.
disable-model-invocation: true
---
```

### SKILL.md body

After the front-matter, write the prompt body. Common structure for a role skill:

1. **Session setup** — the very first action the skill must take (e.g., write `.godotmaker/current_role`).
2. **Resume check** — read `stage.jsonl` and decide whether to proceed, resume, or stop with a message.
3. **Hard rules** — what the skill must never do (often enforced by hooks as a backup).
4. **Steps** — numbered instructions for the work this role does.
5. **Completion** — how to record the role completion event.

Use `$ARGUMENTS` as a placeholder for anything the user passes after the slash command.

---

## Role skill specifics

### File lock — current_role

The very first action of every role skill must be:

```
Write the role name to .godotmaker/current_role.
```

For example, `/gm-build` writes `build`. This is what `check_file_permissions.py` reads to determine which write rules apply for this session.

### Resume check

Every role skill reads `.godotmaker/stage.jsonl` (one JSON object per line, `{"role": X, "ts": Y}`) and decides:

- If the prerequisite role's event is missing → stop and tell the user which command to run first.
- If this role's completion event already exists → tell the user the role is done and suggest the next command.
- Otherwise → proceed (including resume from an interrupted run).

### Completion event format

When a role finishes, it appends one line to `.godotmaker/stage.jsonl`:

```json
{"role": "build", "ts": "2026-04-27T12:00:00Z"}
```

`append_stage_event.py` validates required outputs before appending. On runtimes
that expose direct Write/Edit hooks, `stage_reminder.py` only injects a pointer
to the next role.

### Required outputs and stage_schemas.json

`config/stage_schemas.json` declares what each role must produce before it can record a completion event. The schema is keyed by role name:

```json
{
  "scaffold": {
    "files": ["project.godot"]
  },
  "gdd": {
    "files": ["GDD.md", "PLAN.md", "STRUCTURE.md"]
  },
  "build": {
    "checks": ["plan_all_verified"]
  },
  "evaluate": {
    "files": [".godotmaker/evaluation.json"]
  }
}
```

- `files` — paths (relative to project root) that must exist on disk.
- `checks` — names of programmatic validators run by `completion_gate.py` from the append tool. Current validators include `plan_all_verified` and `gap_archived_unless_handoff`.

If you add a new role, add a corresponding entry here. If your role has no required outputs that can be validated by file existence, omit the entry or leave the object empty.

### Shared reference docs

If the reference doc you are writing into `references/` will also be needed by another skill, put it in `skills/core/_shared/` instead and add an entry to `_shared/manifest.json`. See `docs/contributing/shared-refs.md` for the manifest schema and add/remove flows. Inside your SKILL.md, reference it as `references/<file>.md` (the deployed path — `_shared/` does not exist at runtime).

---

## Reviewer skill specifics

Reviewer skills must have all three files:

```
skills/reviewer/my-domain/
├── SKILL.md        Reviewer prompt
├── gotchas.md      Domain-specific pitfalls (what LLMs get wrong)
└── checklist.md    Systematic checks that map back to gotcha IDs
```

The reviewer sub-agent reads `gotchas.md` and `checklist.md` dynamically based on which Godot classes and APIs appear in the worker's output. There is no static dispatch list — the reviewer picks the relevant domain files itself.

### gotchas.md format

Each entry describes one concrete pitfall:

```markdown
## G1. Short descriptive title [GDScript] [C#]

**Symptom**: What the developer sees go wrong.

**Root cause**: Why Godot behaves this way.

**Correct approach**: The right pattern.

**Wrong approach**: What LLMs typically generate (and why it fails).
```

Tag entries `[GDScript]`, `[C#]`, or both.

### checklist.md format

Checks are numbered and cross-referenced to gotcha IDs:

```markdown
## Static Checks

### S1. Check name → G1
Grep for [pattern]:
- [condition that signals a problem]
- [expected correct pattern]
```

Use `S` prefix for static (grep-based) checks and `R` for runtime checks.

### Reviewer report format

The `check_worker_report.py` hook validates that reviewer reports contain these sections: `### Reviewers Matched`, `### ECS Review`, `### Issues Found`, `### Summary`. The `ECS Review` and `Issues Found` sections must each have at least 50 characters of content — empty or trivial reports are blocked.

---

## Supporting skill specifics

Supporting skills are pure reference content — no slash command, no `disable-model-invocation: true`. They are loaded by other skills via `references/<file>.md`. The `gecs` skill, for example, provides ECS usage patterns and known pitfalls that `gm-build` references.

There is no registration step. `publish.py` copies every directory under `skills/core/` (except `_shared/`) into the target project, and a consumer skill references the supporting skill's content through a `references/` path.

---

## Testing your skill

1. Publish to a scratch project:

   ```bash
   python tools/publish.py /path/to/scratch-game
   ```

2. Open the scratch project in Claude Code and run the slash command.

3. Inspect the outputs:
   - For role skills: check `stage.jsonl`, the expected files in `config/stage_schemas.json`, and that `.godotmaker/current_role` was written correctly.
   - For reviewer skills: check that the report contains all required sections and that the gotcha cross-references are accurate.

4. If the skill references shared docs, run:

   ```bash
   python -m pytest tests/tools/test_publish_shared.py -q
   ```

   to confirm the manifest and deployed paths are consistent.
