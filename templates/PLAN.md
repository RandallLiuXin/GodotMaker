# Game Plan: {Name}

<!-- Decomposed from GDD.md by /gm-gdd. See GDD.md for full game design.
     Scoped to a single tag (see ROADMAP.md). -->

**Tag:** {vX.Y.Z}

## Game Description

{Summary from GDD §1 (Game Overview) and §2 (Core Gameplay Loop).}

## Tag Mechanics

<!-- Game mechanics this tag MUST deliver. Each gets a stable id `<Tag>-M<N>`.
     State gameplay behavior. -->

- [{Tag}-M1] {what mechanic + observable behavior, e.g. "WASD player movement: holding D moves the player right"}
- [{Tag}-M2] {...}
- [{Tag}-M3] {...}

## Inherited Mechanics

<!-- Mechanics from already-shipped tags that THIS tag must keep working.
     Copied forward by /gm-gdd subsequent-mode from previous tags' Tag
     Mechanics sections. If this tag intentionally removes one, drop it
     here AND add a Main Build refactor task that prunes the corresponding
     code/tests. Omit this entire section for the very first tag (v0.1.0). -->

- [v0.1.0-M1] {inherited mechanic id and behavior}
- [v0.1.0-M2] {...}

## Playable Unit

<!-- This tag's player-experienced game content. It is not an input script.
     Describe what the player can do after this tag ships. For each mechanic,
     name the player operation, the expected game effect, and the visible
     content that must appear for screenshot/video verification. -->

- **Player experience:** {what the player can experience after this tag, e.g. "start a run, move through the arena, avoid one enemy, collect the key, and reach the exit"}
- **Unit outcome:** {observable completion, fail, or exit condition reached through normal play}
- **Scenes involved:** {scene names from SCENES.md}

| Mechanic | Player operation / content | Expected effect | Required visible content | Evidence |
|----------|----------------------------|-----------------|--------------------------|----------|
| [{Tag}-M1] | {what the player can do or experience} | {state/gameplay effect after the operation} | {object/UI/state that must appear on screen} | {E2E assertion, screenshot, video frame, or log path} |
| [{Tag}-M2] | {...} | {...} | {...} | {...} |

- **Review focus:** {code paths reviewers should inspect for real runtime gameplay, not stubs or test-only shortcuts}

## Risk Tasks

<!-- Omit this section entirely if no risks identified. -->
<!-- Risk taxonomy for ECS: procedural generation, procedural animation,
     sprite/character animations, complex physics, custom shaders,
     runtime geometry, dynamic navigation, complex camera systems.
     These fail unpredictably and need isolation before main build. -->

### 1. {Risk Feature}
- **Why isolated:** {what makes this algorithmically hard}
- **Approach:** {algorithmic strategy or key constraints}
- **Systems:** {which systems this task implements — e.g., ProceduralTerrainSystem}
- **Components:** {which components this task defines — e.g., TerrainChunk, HeightMap}
- **Verify:**
  - {specific criteria targeting the failure mode}
  - DAG check passes with new systems integrated
  - gdUnit tests cover the core algorithm

### 2. {Risk Feature}
- **Why isolated:** ...
- **Approach:** ...
- **Systems:** ...
- **Components:** ...
- **Verify:** ...

## Main Build

{Game-mechanic functions and integration tasks. Add normal M-series tasks for
the player-facing state, feedback, and presentation needed to play this tag.}

### Build Tasks

| Task | Game Mechanic Function | Player-Facing Outcome | Affected Systems / Scenes / UI | Integration Point | Verify |
|------|------------------------|-----------------------|--------------------------------|-------------------|--------|
| M01 | {mechanic function to implement} | {what the player can do or understand} | {systems, scenes, UI touched} | {playable path connection} | {unit/build/manual check} |
| M02 | {...} | {...} | {...} | {...} | {...} |

### Systems & Components

<!-- List the systems and components touched by the build tasks. -->

| System | Components (reads) | Components (writes) | Purpose |
|--------|--------------------|---------------------|---------|
| MovementSystem | Transform, MovementIntent | Transform | Apply movement to entities |
| RenderSystem | Transform, SpriteComp | — | Project sprite nodes into scene tree |
| ... | ... | ... | ... |

### Assets Needed

<!-- Visual assets the game needs — type, approximate size, visual role. Omit if none. -->

- {asset description}
- **Terrain approach:** Sprite placement (individual scene elements) | N/A

### Verify

- Player input -> entity response feels correct
- Movement direction matches input
- Animation direction matches movement direction
- Physics entities respond to gravity/collision
- UI readable, no overflow or overlap
- No missing textures (magenta/checkerboard)
- {Game-specific checks}
- Gameplay flow matches game description
- No visual glitches, clipping, or placeholder assets
- reference.png consistency: color palette, scale, camera angle, visual density
- DAG check passes (no circular node-creation dependencies)
- All gdUnit tests pass (pure logic systems + materialization systems)
- Optional VQA validation on screenshots

## Task Status

<!-- Update after each task completes. This is the resume point. -->

| # | Task | Status | Notes |
|---|------|--------|-------|
| R1 | {Risk task 1} | pending | |
| R2 | {Risk task 2} | pending | |
| M01 | {mechanic function task} | pending | |
| M02 | {mechanic function task} | pending | |
