---
name: gecs
description: |
  gecs ECS framework API reference — the Entity-Component-System addon for
  Godot 4.x used by this project. Covers Entity, Component, System, World,
  QueryBuilder, Relationship, Observer, CommandBuffer, SystemTimer.
  Use when the task involves ECS architecture: creating entities with components,
  defining component data classes (C_ prefix), writing game logic systems,
  querying entities by component composition, entity relationships or links,
  reactive observers for component changes, safe structural changes during
  iteration, system tick rates, ECS world setup, debugging ECS queries or cache,
  or deferred entity destruction. Also trigger on gecs API calls: q.with_all(),
  ECS.world, ECS.process(), define_components(), cmd.add_component(). gecs has
  zero LLM training data — without this skill all ECS API calls will be
  fabricated. NOT relevant for standard Godot subsystems (physics, animation,
  UI, tilemap, shader, particles, navigation, signals, audio) unless explicitly
  connected to ECS.
---

# gecs — ECS Framework for Godot 4.x

$ARGUMENTS

gecs is the ECS backend for GodotMaker. It has **zero LLM training data coverage** —
all API knowledge must come from this skill.

## Core Concept Mapping

| gecs Class | Godot Base | Key Insight |
|------------|-----------|-------------|
| `Entity` | `extends Node` | Entity IS a Node — lives in scene tree, can have child nodes |
| `Component` | `extends Resource` | Pure data, `@export` properties with defaults, no logic |
| `System` | `extends Node` | Contains game logic, queries entities, placed in scene tree |
| `World` | `extends Node` | Manages all entities/systems, archetype storage, query engine |
| `QueryBuilder` | `extends RefCounted` | Chain API: `with_all`/`with_any`/`with_none`, auto-cached |
| `Relationship` | `extends Resource` | Pair (relation_component, target), archetype-level indexing |
| `Observer` | `extends Node` | Reactive: fires on component add/remove/change events |
| `CommandBuffer` | `extends RefCounted` | Safe structural changes during iteration via `cmd` |
| `ECS` | Autoload singleton | Global access: `ECS.world`, `ECS.process(delta, group)` |

## Quick Start

```gdscript
# --- Component (pure data, extends Resource) ---
class_name C_Health extends Component
@export var current: float = 100.0
@export var maximum: float = 100.0

class_name C_Velocity extends Component
@export var direction: Vector3 = Vector3.ZERO
@export var speed: float = 100.0

# --- Entity (extends Node, define default components) ---
class_name Player extends Entity
func define_components() -> Array:
    return [C_Health.new(), C_Velocity.new()]

func on_ready():
    add_to_group("player")

# --- System (game logic, extends Node) ---
class_name MovementSystem extends System
func query() -> QueryBuilder:
    return q.with_all([C_Velocity])

func process(entities: Array[Entity], components: Array, delta: float) -> void:
    for entity in entities:
        var vel = entity.get_component(C_Velocity)
        var pos = entity.get_component(C_Position)
        pos.value += vel.direction * vel.speed * delta  # Entity is Node, not Node2D!

# --- Main scene processing ---
# main.gd
func _process(delta):
    ECS.process(delta, "input")
    ECS.process(delta, "gameplay")

func _physics_process(delta):
    ECS.process(delta, "physics")
    ECS.process(delta, "run-last")
```

## Naming Conventions

| Type | Class Name | File Name | Example |
|------|-----------|-----------|---------|
| Component | `C_Name` | `c_name.gd` | `C_Health` / `c_health.gd` |
| System | `NameSystem` | `s_name.gd` | `MovementSystem` / `s_movement.gd` |
| Entity | `Name` | `e_name.gd` | `Player` / `e_player.gd` |
| Observer | `NameObserver` | `o_name.gd` | `HealthUIObserver` / `o_health_ui.gd` |
| Relationship component | `R_Action` | `r_action.gd` | `R_ChildOf` / `r_child_of.gd` |

## Common Operations

### Entity

```gdscript
# Create programmatically
var entity = Player.new()
ECS.world.add_entity(entity)

# Instantiate from scene prefab (.tscn with Entity root)
var entity = preload("res://entities/e_player.tscn").instantiate()
get_tree().current_scene.add_child(entity)
ECS.world.add_entity(entity)

# Component operations (pass CLASS to get/has, INSTANCE to add/remove)
entity.add_component(C_Health.new(100))
var health = entity.get_component(C_Health)      # returns instance or null
var has = entity.has_component(C_Health)           # bool check
entity.remove_component(health)                    # pass the instance

# Enable/disable
entity.enabled = false     # excluded from queries
ECS.world.disable_entity(entity)
ECS.world.enable_entity(entity)

# Destroy (calls on_destroy, queue_free, cleans up relationships)
ECS.world.remove_entity(entity)
```

### Query

```gdscript
# In a System — use q shorthand
func query() -> QueryBuilder:
    return q.with_all([C_Health, C_Velocity])   # must have ALL
             .with_any([C_Player, C_Enemy])     # must have at least ONE
             .with_none([C_Dead])                # must NOT have
             .enabled()                           # only enabled entities

# Batch component access (faster — avoids per-entity get_component):
func query() -> QueryBuilder:
    return q.with_all([C_Velocity]).iterate([C_Velocity])

func process(entities: Array[Entity], components: Array, delta: float):
    var velocities = components[0]   # Array of C_Velocity, same order as entities
    for i in entities.size():
        var pos = entities[i].get_component(C_Position)
        pos.value += velocities[i].direction * delta  # Entity is Node, not Node2D!

# Standalone query (outside a System):
var enemies = ECS.world.query.with_all([C_Health, C_Enemy]).execute()
var player = ECS.world.query.with_all([C_Player]).execute_one()
```

### CommandBuffer (safe structural changes during iteration)

```gdscript
class_name LifetimeSystem extends System

func query():
    return q.with_all([C_Lifetime])

func process(entities: Array[Entity], components: Array, delta: float):
    for entity in entities:          # safe forward iteration
        var lt = entity.get_component(C_Lifetime)
        lt.time -= delta
        if lt.time <= 0:
            cmd.remove_entity(entity)                     # queued
        if should_upgrade(entity):
            cmd.remove_component(entity, C_OldState)      # queued
            cmd.add_component(entity, C_NewState.new())   # queued
    # auto-executes after system completes (FlushMode.PER_SYSTEM default)
```

### Relationships

```gdscript
# Add a relationship
entity.add_relationship(Relationship.new(R_ChildOf.new(), parent_entity))

# Query entities with a relationship
var children = ECS.world.query.with_relationship([
    Relationship.new(R_ChildOf.new(), parent_entity)
]).execute()

# Wildcard query (any target)
var has_allies = entity.has_relationship(Relationship.new(R_AllyTo.new(), null))

# Remove with limit
entity.remove_relationship(Relationship.new(R_Buff.new(), null), 1)   # remove 1
entity.remove_relationship(Relationship.new(R_Effect.new(), null))    # remove all
```

### System Groups & Scene Architecture

```
Main.tscn
+-- World (World node)
+-- Systems (Node)
|   +-- input (SystemGroup)
|   |   +-- PlayerControlsSystem
|   +-- gameplay (SystemGroup)
|   |   +-- HealthSystem
|   |   +-- DeathSystem
|   +-- physics (SystemGroup)
|   |   +-- MovementSystem
|   |   +-- CollisionSystem
|   +-- run-last (SystemGroup)
|       +-- PendingDeleteSystem
+-- Entities (Node — spawned entities go here)
+-- Level (Node3D — level geometry)
```

SystemGroup nodes auto-assign their name as the `group` property of child Systems.

## Reference Files

Read the relevant file when you need detailed API beyond this quick reference:

| Need | File | When to read |
|------|------|-------------|
| Entity lifecycle, prefabs, spawning | [`references/entity.md`](references/entity.md) | Creating entities, scene prefab setup, on_ready/on_destroy |
| Component design, @export patterns | [`references/component.md`](references/component.md) | Defining new components, constructor patterns |
| System impl, CommandBuffer, timers | [`references/system.md`](references/system.md) | Writing systems, sub_systems, tick rates, deps, parallel |
| World setup, entity management | [`references/world.md`](references/world.md) | World init, add/remove entities/systems, process groups |
| Queries, Relationships, Observers | [`references/query.md`](references/query.md) | Complex queries, entity linking, reactive systems |
| Debug tools, profiling | [`references/debug.md`](references/debug.md) | Runtime inspection, editor debugger, performance |
| Naming, file org, scene architecture | [`references/patterns.md`](references/patterns.md) | Project structure, cross-cutting patterns, ECS_DESIGN adaptation |

## MANDATORY: Read gotchas.md Before Writing ECS Code

**Before writing ANY gecs code**, read [`gotchas.md`](gotchas.md). It contains 19 hard-won pitfalls with wrong→correct code examples.

**If you hit a compile or runtime error**, check `gotchas.md` first — most ECS errors are covered there.

## Critical Gotchas (summary)

1. **All `@export` properties MUST have default values** — Godot errors on Resource export without defaults
2. **`get_component()` takes the CLASS, not an instance** — `entity.get_component(C_Health)` not `entity.get_component(health_instance)`
3. **Never put logic in Components** — all behavior belongs in Systems
4. **Use `cmd` for structural changes during iteration** — direct add/remove during `process()` causes entity skipping
5. **Avoid `with_group()` in queries** — ~50x slower than `with_all([C_Tag])` due to SceneTree traversal. Use tag components instead
6. **`define_components()` must return fresh `.new()` instances** — returning cached/shared instances causes state leakage between entities
7. **Entity extends Node, NOT Node2D** — `entity.position` does NOT work. Store position in a `C_Position` component. See gotchas.md G1
8. **Component `_init()` must have default params** — `func _init(v: float = 0.0)` so `Component.new()` works for duplication
9. **Components are inaccessible before `add_entity()`** — `get_component()` returns null until entity enters scene tree. See gotchas.md G2
10. **Never call `system.process()` directly in tests** — causes Array[Entity] type error + CommandBuffer not flushed. **Never write `test_system_has_query`** — `q` is null outside World. See G10, G14
11. **`add_system()` second param is `bool`, not group name** — set `system.group` before `add_system()`. See G15
12. **`world.process(delta)` without group skips grouped systems** — must pass group name. See G16
13. **NodePath `@export` in `.tscn` unreliable for World** — set `entity_nodes_root`/`system_nodes_root` in `_init()`. See G17
14. **Area2D overlap data stale in `_process`** — overlap systems must run in `physics` group. See G18
15. **`:=` type inference fails with ternary + null** — use explicit type annotation. See G19
