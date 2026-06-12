# Game Design Document: {Name}

<!-- This is a REFERENCE template. Sections are flexible:
     - Skip sections that don't apply to this game type
     - Add custom sections if the game needs them
     - The game-planner interview will determine which sections to fill -->

## 1. Game Overview

- **Title:** {working title}
- **Genre:** {platformer, shooter, puzzle, RPG, tower defense, etc.}
- **Perspective:** {2D side-view / 2D top-down / 2D fixed/grid}
- **Platform:** Godot 4.x (Desktop)
- **One-line pitch:** {one sentence that captures the core fantasy}
- **Target session length:** {how long is one play session}

## 2. Core Gameplay Loop

<!-- What the player DOES, moment to moment, session to session. -->

- **Moment-to-moment:** {what does the player do every few seconds?}
- **Session loop:** {start → play → end — what's the arc of one session?}
- **Progression loop:** {how does the game evolve across sessions? skip if single-session}

## 3. Mechanics

### Core Mechanics

<!-- Must-have mechanics for the game to function. -->

| Mechanic | Player Action | Game Response / Feedback |
|----------|--------------|------------------------|
| {e.g., Jump} | {press Space} | {character jumps, landing particles} |
| ... | ... | ... |

### Additional Mechanics

<!-- Optional mechanics that may be assigned to playable units later. -->

- {mechanic}: {brief description}
- ...

## 4. Game World & Setting

<!-- Skip for abstract games (Tetris, etc.) -->

- **Theme / Setting:** {fantasy forest, sci-fi space station, etc.}
- **Mood / Atmosphere:** {dark and tense, bright and cheerful, etc.}
- **Art style:** {pixel art / vector / hand-painted / cartoon / placeholder}
- **Visual mode:** {pixel art / non-pixel 2D}
- **Target viewport:** {e.g., 1280x720 for non-pixel 2D, 480x270 for pixel art}
- **Gameplay actor screen presence:** {default actor height as % of viewport height and px at target viewport}
- **Color palette:** {dominant colors, warm/cool}
- **Visual references:** {description of intended look, or "see user-provided assets"}

## 5. Characters & Entities

<!-- Maps directly to ECS Components. Skip for games without characters. -->

### Player Character

- **Abilities:** {what can the player do?}
- **Constraints:** {what limits the player?}
- **Visual:** {sprite description or reference; target gameplay height}

### Enemies / NPCs

| Entity | Behavior | Visual | Target Gameplay Height |
|--------|----------|--------|------------------------|
| {e.g., Slime} | {patrol, chase on sight} | {green blob, readable silhouette} | {e.g., 7% viewport height / 50px at 720p} |
| ... | ... | ... | ... |

### Interactive Objects

- {object}: {what it does when player interacts}
- ...

## 6. Level / Scene Design

<!-- Skip for endless/procedural games, or describe generation rules instead. -->

| Level/Scene | Objective | New Mechanic Introduced | Difficulty |
|-------------|-----------|------------------------|------------|
| {Level 1} | {reach the exit} | {basic movement} | {easy} |
| ... | ... | ... | ... |

**Difficulty progression:** {how difficulty ramps up}

## 7. UI / UX Design

### HUD

- {element}: {purpose} — e.g., Health bar: top-left, shows player HP

### Menu Flow

```
Main Menu → Start Game → Gameplay → Pause Menu → Resume / Quit
                                  → Game Over → Retry / Main Menu
```

### Juice / Feedback

- {screen shake on hit, particle effects, hit flash, etc.}

## 8. Audio Direction

<!-- Users must provide their own audio files. This section describes WHAT is needed. -->

### Music

| Scene/Context | Mood | Notes |
|--------------|------|-------|
| {Main menu} | {calm, inviting} | {loop} |
| {Gameplay} | {energetic} | {loop} |
| ... | ... | ... |

### Sound Effects

- {action}: {description} — e.g., Jump: short whoosh, 0.2s
- ...

## 9. Art Asset Requirements

<!-- What visual assets the game needs. Filled during /gm-gdd; resolved during /gm-asset. -->

### Required Assets

| Category | Asset | Description | Provided by User? |
|----------|-------|-------------|-------------------|
| Sprite | {player} | {player character sprite/sheet} | {yes/no} |
| Sprite | {enemy} | {basic enemy} | {yes/no} |
| Background | {sky} | {background layer} | {yes/no} |
| UI | {buttons} | {menu buttons} | {yes/no} |
| ... | ... | ... | ... |

### Art Style Constraints

- If user provides art assets: **all AI-generated assets MUST match the user's style** (color palette, line weight, proportions, atmosphere)
- If no user art: AI generates based on Art Direction in Section 4

## 10. Scope & Playable Units

### Playable Unit Candidates

<!-- Each candidate is a player-experienced chunk that can become one roadmap tag. -->

| Candidate | Player Experience | Mechanics Included | Completion / Fail / Exit |
|-----------|-------------------|---------------------|--------------------------|
| {unit name} | {what the player can experience} | {mechanics involved} | {how this unit resolves or exits} |
| ... | ... | ... | ... |

### Deferred (future versions)

- {idea 1}
- ...

### Content Volume

- **Levels / Scenes:** {count}
- **Enemy types:** {count}
- **Item types:** {count}
