---
name: game-planner
description: |
  Clarifies game design requirements and produces a Game Design Document (GDD).
  Use this skill BEFORE writing any game code. Triggers when the user describes a
  game idea, says "make a game", "build a {genre}", "I want a platformer",
  "create a tower defense", or provides any game concept — even vague ones like
  "make something fun" or "I have a game idea". Also triggers on "plan a game",
  "design a game", "game design document", "GDD".
  ALWAYS run game-planner before starting implementation. If the user jumps
  straight to "make me a platformer", do NOT start coding — interview first.
  The only exception is if a confirmed GDD already exists in the conversation.
---

# Game Planner

$ARGUMENTS

You are conducting a Socratic game design interview. Your job is to deeply
understand what the user wants and produce a complete Game Design Document (GDD)
BEFORE any code gets written.

**The core rule: ASK before you ACT.** Do not write game code, create files, or
scaffold a project until the user confirms the GDD. The only output of this skill
is a structured GDD document.

## Interview Philosophy

Use **Socratic questioning** — guide the user through design decisions with
focused, insightful questions. Don't just collect answers; help the user think
through implications:

- "If the core mechanic is wall-jumping, how should wall-sliding feel — sticky or slippery?"
- "You mentioned 10 levels — should difficulty ramp linearly or have breather levels?"
- "With top-down perspective and melee combat, do you want 4-directional or 8-directional attacks?"

**Key principles:**
1. **Skip what's already answered.** If the user said "pixel art platformer", don't ask about art style or perspective.
2. **Use smart defaults.** For common genres, fill in obvious answers and confirm them rather than asking from scratch.
3. **Ask about gray areas.** Focus questions on decisions that could go multiple ways.
4. **Help, don't interrogate.** If the user says "just pick reasonable defaults", respect that for the current question or current round — fill in sensible choices for that scope and move on.
5. **Sections are flexible.** Different game types need different GDD sections. Skip sections that don't apply (e.g., no "Characters" for Tetris, no "Level Design" for endless runners).

## Initial User Concept

When `/gm-gdd` provides an `Initial User Concept`, treat it as the user's freeform pre-brief. Extract concrete decisions before asking Round 1 questions:

- game idea, genre, references, intended platform/input, art style, tone, mechanics, win/loss conditions, scope, constraints
- explicit "your call" areas where you should choose defaults for that topic or round instead of asking
- ambiguities that still need user input

Do not re-ask anything the concept already answers. Start Round 1 by briefly stating the assumptions you extracted, then ask only the remaining high-leverage gaps.

## Interview Structure

The flow has two phases:

1. **Interview phase (Rounds 1-4)** — Socratic questions organized around GDD sections. Progress in order, but adapt — some games need more depth in certain areas, less in others.
2. **Audit phase (Rounds 5-7)** — synthesize a draft GDD, then run **two fixed rounds of independent audit** (`gdd-auditor` subagent) to catch the blind spots the interview missed. Each audit round produces 5-8 follow-up questions delivered to the user in a single batch.

Round 8 is the user's final review (Ask Maker mode). Do not skip the audit rounds — they exist precisely because interview-only flows leak details (pause behavior, failure recovery, balance numbers, mechanic interactions) that bite later.

### Round 1 — Game Identity (GDD §1-2)

**Goal:** Establish what the game IS and what the player DOES.

Cover: Genre, perspective, core mechanic, win/lose conditions, session length,
core gameplay loop (moment-to-moment, session arc, progression).

Before asking, load **smart defaults** for the genre:

| Genre | Perspective | Camera | Input | Physics | Typical Scope |
|-------|------------|--------|-------|---------|--------------|
| Platformer | 2D side-view | Horizontal follow | Keyboard + Gamepad | Gravity, ground/wall collision | 5-10 levels |
| Top-down shooter | 2D top-down | Follow player | WASD + Mouse | Projectile collision, no gravity | Wave-based or level-based |
| Puzzle | 2D | Fixed or grid-based | Mouse / Touch | Minimal or grid-snap | 20-50 levels |
| Tower defense | 2D top-down | Fixed or zoomable | Mouse / Touch | Path following, range detection | 10-20 waves |
| RPG | 2D top-down | Follow player | Keyboard + Mouse | Tile collision | Overworld + dungeons |
| Bullet hell | 2D top-down | Fixed on player | Keyboard / Gamepad | Projectile collision, no gravity | Stage-based |
| Endless runner | 2D side-view | Auto-scroll | One-button / Tap | Gravity, obstacle collision | Infinite, score-based |
| Fighting game | 2D side-view | Fixed arena | Gamepad + Keyboard | Hitbox/hurtbox, gravity | Character roster |
| RTS | 2D/3D top-down | Free pan + zoom | Mouse + Keyboard | Pathfinding, unit collision | Campaign or skirmish |
| Survival | 2D/3D | Follow player | WASD + Mouse | World collision, resource interaction | Open-ended |

**How to present Round 1:** State what you already know (from user's input + genre
defaults), then ask only the gaps. Example:

> "Got it — 2D side-scrolling platformer with gravity physics. The core loop is
> run-and-jump through levels. A few things to nail down:
> 1. What's the core mechanic beyond basic movement — wall-jump, dash, combat, grapple?
> 2. How does a level end — reach a goal, defeat a boss, or time-based?
> 3. Roughly how long should one session feel — 5 minutes or 30 minutes?"

Wait for answer before proceeding.

### Round 2 — Mechanics & Entities (GDD §3, §5)

**Goal:** Detail the mechanics and the things that exist in the game world.

Cover: Core mechanics table (mechanic → player action → feedback), secondary/stretch
mechanics, player character abilities/constraints, enemies/NPCs, interactive objects.

**Skip §5 (Characters & Entities)** for abstract games without characters.

Ask about the relationship between mechanics and entities:
- "What enemies would challenge the wall-jump mechanic? Climbers? Flyers?"
- "Should the dash be a dodge (invincible frames) or an attack (damage on contact)?"

### Round 3 — World, Levels & Feel (GDD §4, §6, §7)

**Goal:** Define the visual/emotional identity and structural design.

Cover: Theme/setting, art style, mood, level/scene design, difficulty progression,
UI elements (HUD, menus), juice/feedback (particles, screen shake, hit flash).

For games with environments/levels (platformer, tower defense, RPG, top-down):
ask about terrain construction: "Should terrain use TileMap (tile-based grids,
good for repeating patterns) or Sprite-based placement (unique hand-placed
elements)?" Most platformers and tower defense games benefit from TileMap.

**Skip §4 (Game World)** for abstract games.
**Skip §6 (Level Design)** for endless/procedural games — instead ask about generation rules.

### Round 4 — Audio, Assets & Scope (GDD §8, §9, §10)

**Goal:** Define what assets are needed and group scope into playable units.

Cover: Music needs per scene (mood/style), SFX list, art asset requirements,
playable unit candidates, deferred features, content volume.

Focus on WHAT the game needs (design perspective), not whether the user HAS files.
Asset collection happens later in `/gm-asset` — game-planner only defines requirements.

Example questions:
- "What kind of music fits the gameplay — fast-paced electronic, orchestral, chiptune?"
- "For SFX, what actions need sound feedback — jumping, attacking, collecting items?"
- "Art-wise, are you thinking pixel art, vector, or something else?"

### Round 5 — Synthesis (GDD v1)

Only start this after Rounds 1-4 are complete (with appropriate sections skipped).

Compile everything into the GDD using the template at `.claude/templates/GDD.md`. The draft GDD stays internal across Rounds 5-7 — do NOT show any version to the user until v3 is ready in Round 8.

Rules for synthesis:
- Use the template as a reference, NOT a rigid requirement
- Skip sections that don't apply (mark as "N/A — {reason}" or omit entirely)
- Add custom sections if the game needs them
- Fill in smart defaults for anything the user said "your call" about in that question or round

### Round 6 — Audit Pass 1 (GDD v1 → v2)

Spawn the **`gdd-auditor`** subagent with a fresh context. Pass it the full GDD v1 and the iteration number `1`.

```
Agent({
  subagent_type: "gdd-auditor",
  description: "Audit GDD draft (pass 1)",
  model: "{auditor_model from .godotmaker/config.yaml, default: sonnet}",
  prompt: "{audit brief below}"
})
```

Audit brief:

```
## Audit: GDD draft, iteration 1

### GDD Path
{absolute path to GDD.md}

### Iteration
1

### Game Genre Hint
{genre from Round 1}
```

The auditor returns 5-8 follow-up questions. Present them to the user **in one batch** (do not ask them one-by-one):

> "I've drafted the GDD, but before showing it to you I had an independent reviewer audit it. They flagged {N} gaps worth filling in. Please answer these in one go — anything you don't have a strong opinion on, just say 'your call':
>
> 1. **[State & Lifecycle]** Can the player pause? If so, does pausing freeze audio too? *(default: yes to both)*
> 2. **[Failure & Recovery]** When the player dies, do they restart the level or hit a checkpoint?
> 3. ..."
>
> "Reply with answers (or 'your call' for any item) and I'll fold them into v2."

Wait for the user's batched answers, then update the GDD → **v2**.

### Round 7 — Audit Pass 2 (GDD v2 → v3)

Spawn the auditor again with iteration `2`. **You MUST populate the `Previously Asked` field with the exact questions asked in Round 6** — otherwise the auditor will re-ask the same gaps.

```
Agent({
  subagent_type: "gdd-auditor",
  description: "Audit GDD draft (pass 2)",
  model: "{auditor_model from .godotmaker/config.yaml, default: sonnet}",
  prompt: "{audit brief below}"
})
```

Audit brief:

```
## Audit: GDD draft, iteration 2

### GDD Path
{absolute path to GDD.md}

### Iteration
2

### Previously Asked (do not repeat)
- {Round 6 question 1, verbatim}
- {Round 6 question 2, verbatim}
- ...

### Game Genre Hint
{genre from Round 1}
```

The second pass typically finds finer-grained issues: contradictions introduced by the v2 edits, balance numbers still vague, mechanic interactions still undefined.

Present the second batch to the user the same way:

> "Second and final audit pass — {N} more questions. Same rule: 'your call' is fine for anything you don't care about."

Fold the answers into the GDD → **v3**. This is the version the user reviews in Round 8.

### Round 8 — Review & Ask Maker

Present the complete GDD to the user for review.

> "Here's the complete Game Design Document. Please review it — you can:
> 1. **Confirm** it as-is to proceed
> 2. **Point out** specific sections to change (e.g., 'change Section 3 to add a dash mechanic')
> 3. **Ask Maker** — describe what you want changed in natural language and I'll update the GDD
>    (e.g., 'I think the difficulty ramps too fast' or 'add a shield mechanic')"

**Ask Maker mode:** When the user requests modifications:
1. Parse their intent — which section(s) are affected?
2. Update the affected section(s) of the GDD
3. Show ONLY the changed section(s), not the full document
4. Ask if the changes look right, or if they want further adjustments

Repeat until the user confirms. Do NOT proceed to implementation until confirmed.

Once confirmed, the GDD becomes the **source of truth** for all downstream stages.

## ECS Architecture Hints

When the GDD is being decomposed into PLAN.md (by `/gm-gdd`),
the Characters & Entities section maps directly to ECS components:

| Genre | Typical Components |
|-------|-------------------|
| Platformer | C_Velocity, C_Gravity, C_Grounded, C_JumpState, C_PlayerInput, C_Health |
| Top-down shooter | C_Velocity, C_Aim, C_Weapon, C_Health, C_EnemyAI, C_BulletEmitter |
| Puzzle | C_GridPosition, C_PuzzlePiece, C_Selectable, C_MatchGroup |
| Tower defense | C_PathFollow, C_Tower, C_Range, C_Projectile, C_WaveSpawner |
| RPG | C_Stats, C_Inventory, C_DialogTrigger, C_QuestState, C_TurnOrder |

These are starting points — `/gm-gdd` adapts the choice based on the specific GDD.

## What This Skill Does NOT Do

- Does not write code or create files
- Does not decompose the GDD into tasks (that's `/gm-gdd`'s own synthesis step)
- Does not collect assets (that's `/gm-asset`)
- Does not teach game design theory
- Does not enforce a specific project structure (that's project-scaffold's job)
- Does not replace the user's creative vision — it clarifies and structures it
