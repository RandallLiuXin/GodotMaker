# {Project Name}

<!-- Scoped to a single tag (see ROADMAP.md). Captures the structure as
     it exists at the END of this tag — i.e., previous tags' systems +
     this tag's additions / refactors. -->

**Tag:** {vX.Y.Z}

## Dimension: 2D

## Input Actions

| Action | Keys |
|--------|------|
| move_left | A, Left |
| move_right | D, Right |
| jump | Space |
| fire | Mouse Left |

## Component Registry

<!-- All components in the game. Each component is pure data — no methods, no logic. -->
<!-- Field types use GDScript types: int, float, String, Vector2, Vector3, bool, Array, Dictionary -->

### Core Components

| Component | Field | Type | Default | Description |
|-----------|-------|------|---------|-------------|
| Transform | position | Vector2 | Vector2.ZERO | World position |
| Transform | rotation | float | 0.0 | Rotation in radians |
| Transform | scale | Vector2 | Vector2.ONE | Scale factor |
| NodeRef | node | Node | null | Reference to root Node in scene tree |

### Game Components

<!-- Add game-specific components here. -->

| Component | Field | Type | Default | Description |
|-----------|-------|------|---------|-------------|
| Health | current | int | 100 | Current hit points |
| Health | max | int | 100 | Maximum hit points |
| MovementIntent | direction | Vector2 | Vector2.ZERO | Desired movement direction |
| MovementIntent | speed | float | 200.0 | Movement speed |
| SpriteComp | texture_path | String | "" | Path to sprite texture |
| SpriteComp | animation | String | "idle" | Current animation name |
| PhysicsComp | shape | String | "circle" | Collision shape type |
| PhysicsComp | radius | float | 16.0 | Collision radius |
| ... | ... | ... | ... | ... |

### Tag Components

<!-- Tags have no fields — they mark entity archetypes or states. -->

| Tag | Purpose |
|-----|---------|
| PlayerTag | Identifies the player entity |
| EnemyTag | Identifies enemy entities |
| DestroyTag | Marks entity for end-of-frame destruction |
| ... | ... |

## System Schedule

<!-- All systems, grouped by phase, in execution order within each phase.
     Each system declares its data dependencies for DAG validation.
     "creates_node" and "requires_node" are for init-time node creation ordering. -->

### Phase: Input

| Order | System | Reads | Writes | Creates Node | Requires Node |
|-------|--------|-------|--------|-------------|---------------|
| 1 | InputSystem | PlayerTag | MovementIntent | — | — |

### Phase: Logic

| Order | System | Reads | Writes | Creates Node | Requires Node |
|-------|--------|-------|--------|-------------|---------------|
| 2 | MovementSystem | MovementIntent | Transform | — | — |
| 3 | AISystem | Transform, EnemyTag | MovementIntent | — | — |
| 4 | CombatSystem | Transform, Health | Health, DestroyTag | — | — |
| ... | ... | ... | ... | ... | ... |

### Phase: Materialization

<!-- Systems that project ECS data into Godot scene tree. -->

| Order | System | Reads | Writes | Creates Node | Requires Node |
|-------|--------|-------|--------|-------------|---------------|
| 10 | RenderSystem | Transform, SpriteComp | — | Sprite2D | — |
| 11 | PhysicsProjectionSystem | Transform, PhysicsComp | — | CollisionShape2D | — |
| 12 | AnimationSystem | SpriteComp | — | AnimationPlayer | Sprite2D |
| ... | ... | ... | ... | ... | ... |

### Phase: Cleanup

| Order | System | Reads | Writes | Creates Node | Requires Node |
|-------|--------|-------|--------|-------------|---------------|
| 99 | DestructionSystem | DestroyTag, NodeRef | — | — | — |

## Scene Markers

<!-- Marker nodes placed in Godot scenes. The runtime converter reads these
     and creates ECS entities with the listed component combinations. -->

| Marker Type | Components | Notes |
|-------------|------------|-------|
| PlayerSpawnMarker | Transform, PlayerTag, Health, MovementIntent, SpriteComp, PhysicsComp | Single instance per level |
| EnemySpawnerMarker | Transform, Spawner{wave, interval}, EnemyTag | Spawns waves of enemies |
| PickupMarker | Transform, PickupItem{type, value}, SpriteComp | Collectible items |
| TriggerZoneMarker | Transform, Area, TriggerEvent{id} | Event triggers |
| PatrolNodeMarker | Transform, PatrolPoint{order} | AI patrol waypoints |
| ... | ... | ... |

## Entity Archetypes

<!-- Common entity templates as component combinations.
     These are the "prefab" equivalents in ECS — not Godot scenes,
     but named sets of components that spawn together. -->

### Player
- Transform, PlayerTag, Health, MovementIntent, SpriteComp, PhysicsComp, NodeRef

### Enemy
- Transform, EnemyTag, Health, AIMovement, SpriteComp, PhysicsComp, NodeRef

### Projectile
- Transform, Velocity, Damage, SpriteComp, PhysicsComp, NodeRef
- Lifetime: destroyed after {N} seconds or on collision

### Pickup
- Transform, PickupItem, SpriteComp, NodeRef

<!-- Add more archetypes as needed. -->

## Node Projection

<!-- Which systems create which Godot nodes for which components.
     This is the "materialization" reference — how ECS data becomes visible. -->

| System | When Component Added | Node Created | Parent |
|--------|---------------------|-------------|--------|
| RenderSystem | SpriteComp | Sprite2D | Entity root Node |
| PhysicsProjectionSystem | PhysicsComp | CollisionShape2D | Entity root Node |
| AnimationSystem | AnimComp | AnimationPlayer | Entity root Node |
| ... | ... | ... | ... |

<!-- Node lifecycle protocol:
     - on_construct: check for existing disabled node first, enable if found, else create new
     - on_destroy (component removed): disable node, do NOT free
     - Entity destruction: DestructionSystem queue_frees root Node (all children freed) -->

## Build Order

<!-- Dependency-aware implementation order.
     Pure logic systems first (no node dependencies), then materialization systems.
     Within each group, leaf dependencies before consumers. -->

1. Component definitions (all components registered)
2. DAG check tool setup
3. Pure logic systems (no node interaction):
   - InputSystem
   - MovementSystem
   - AISystem
   - CombatSystem
4. Materialization systems (create/manage nodes):
   - RenderSystem (creates Sprite2D)
   - PhysicsProjectionSystem (creates CollisionShape2D)
   - AnimationSystem (requires Sprite2D, creates AnimationPlayer)
5. DestructionSystem (always last)
6. Scene marker converter
7. Integration wiring + gdUnit integration tests

## Asset Hints

<!-- Visual assets the architecture needs. The asset planner uses these. -->

- {asset type} ({size/description}, {visual role})
- Player sprite (32x32 character, 4-direction walk cycle)
- Enemy sprite (32x32 creature)
- Background (parallax layers, sky + distant terrain)
