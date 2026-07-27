---
name: phantom-camera
description: |
  Guidance for using the optional Phantom Camera Godot addon in generated projects.
  Use when a Godot 4 game explicitly opts into Phantom Camera, already has the
  addon installed, or needs camera behavior that is cleaner with multiple virtual
  cameras than with a hand-written Camera2D script. Do not require this addon for
  ordinary projects that can be served by Godot's built-in Camera2D/Camera3D.
---

# Phantom Camera

$ARGUMENTS

Phantom Camera is an optional Godot 4 addon for advanced camera behavior inspired
by Cinemachine. Prefer it when the game needs several camera rigs, smooth
transitions, framed/dead-zone following, group/path following, camera shake, or
cutscene-style camera moves. Keep using plain `Camera2D` / `Camera3D` when the
request is a simple static camera, a one-off follow script, or when the generated
project has not opted into optional addons.

## Opt-in Rules

Use Phantom Camera only when one of these is true:

1. The user asks for Phantom Camera by name.
2. `addons/phantom_camera/plugin.cfg` exists and the plugin is enabled in
   `project.godot`.
3. The GDD or task explicitly calls for advanced camera behavior and the user or
   project config allows adding optional addons.

Do not silently add the addon to every scaffolded project. If the addon is not
present, document the dependency and either ask for approval before installing it
or implement a built-in camera fallback.

Compatibility note: before installing, check the selected Phantom Camera release
or `addons/phantom_camera/plugin.cfg` for its supported Godot version. If the
project is pinned below the addon's minimum, use built-in camera code instead.

## Scene Pattern

For 2D, use this baseline scene shape:

```text
World
|-- Player
|-- Camera2D
|   `-- PhantomCameraHost
|-- PhantomCamera2DFollow
`-- PhantomCamera2DZone
```

For 3D, mirror the same structure with `Camera3D`, `PhantomCameraHost`, and
`PhantomCamera3D`.

The `PhantomCameraHost` should be a child of the real `Camera2D` / `Camera3D`.
Each `PhantomCamera2D` or `PhantomCamera3D` stores a camera behavior. The active
camera is selected by priority: raise one PCam's priority to activate it and
lower it when leaving that context.

## 2D Follow Camera

Use a follow PCam for a player or other primary target. Glued follow is the
lightest mode. Framed follow is better for platformers and arena games because
the dead zone prevents the camera from drifting on every small movement.

```gdscript
extends Node2D

@onready var player: Node2D = $Player
@onready var follow_pcam: PhantomCamera2D = $PhantomCamera2DFollow

func _ready() -> void:
    follow_pcam.set_follow_target(player)
    follow_pcam.set_follow_damping(true)
    follow_pcam.set_follow_damping_value(Vector2(0.2, 0.2))
    follow_pcam.set_tween_duration(0.35)
    follow_pcam.set_priority(20)
```

When the follow target is a physics body and the project runs on Godot 4.4 or
newer, enable Physics Interpolation in Project Settings to reduce jitter. On
older projects, follow a visual child that updates in `_process` instead of the
physics body itself.

## Camera Zones

Use camera zones when an area of the map needs different zoom, framing, or
camera limits.

```text
CameraZone2D
|-- CollisionShape2D
`-- PhantomCamera2DZone
```

```gdscript
extends Area2D

@export var active_priority := 40
@export var inactive_priority := 0

@onready var zone_pcam: PhantomCamera2D = $PhantomCamera2DZone

func _on_body_entered(body: Node2D) -> void:
    if body.is_in_group("player"):
        zone_pcam.set_priority(active_priority)

func _on_body_exited(body: Node2D) -> void:
    if body.is_in_group("player"):
        zone_pcam.set_priority(inactive_priority)
```

Keep the default follow PCam at a lower priority, such as `20`, so entering a
zone cleanly takes over and exiting returns control to the normal camera.

## Transitions

Set per-PCam tween settings instead of writing custom interpolation between
cameras. Use short durations for gameplay contexts and longer durations for
cinematic reveals.

```gdscript
func focus_boss_intro() -> void:
    $PhantomCamera2DPlayer.set_priority(10)
    $PhantomCamera2DBoss.set_tween_duration(1.0)
    $PhantomCamera2DBoss.set_priority(50)

func return_to_player() -> void:
    $PhantomCamera2DBoss.set_priority(0)
    $PhantomCamera2DPlayer.set_priority(20)
```

If several PCams should share the same curve and duration, create one
`PhantomCameraTween` resource and assign it to each PCam with
`set_tween_resource()`.

## Camera Shake

Use Phantom Camera noise for sustained shake tied to a PCam, such as a storm,
rumbling machinery, or low-health effect. Use a noise emitter for one-shot events
such as explosions or heavy impacts when the addon is present.

```gdscript
@onready var follow_pcam: PhantomCamera2D = $PhantomCamera2DFollow

func start_danger_shake(noise: PhantomCameraNoise2D) -> void:
    follow_pcam.set_noise(noise)

func stop_danger_shake() -> void:
    follow_pcam.set_noise(null)
```

Do not stack several continuous noise sources on the same PCam unless the design
really needs it. Keep gameplay readability ahead of spectacle.

## Cutscene Camera Moves

For cutscenes, create dedicated PCams at named positions and switch priority as
the sequence advances. This keeps camera logic visible in the scene tree and
avoids mixing story timing into the player controller.

```gdscript
extends Node

@onready var player_pcam: PhantomCamera2D = %PhantomCamera2DPlayer
@onready var gate_pcam: PhantomCamera2D = %PhantomCamera2DGateReveal

func play_gate_reveal() -> void:
    player_pcam.set_priority(10)
    gate_pcam.set_tween_duration(1.25)
    gate_pcam.set_priority(60)
    await gate_pcam.tween_completed
    await get_tree().create_timer(0.8).timeout
    gate_pcam.set_priority(0)
    player_pcam.set_priority(20)
```

For longer authored sequences, drive PCam priority, target positions, and zoom
from `AnimationPlayer` or Phantom Camera's tween director rather than writing a
large procedural timeline.

## Common Camera Test Pass

When a generated game opts into Phantom Camera, include a small camera test pass
that exercises the common camera designs the game actually uses. This can be a
manual smoke test scene, a documented playtest route, or an automated gameplay
test when the project already has an end-to-end runner.

Cover these scenarios when they are relevant to the genre:

| Scenario | What to verify |
|----------|----------------|
| Player follow | The camera tracks the player without jitter, keeps the player readable, and does not overshoot during starts, stops, jumps, or direction changes. |
| Camera zone | Entering a trigger raises the zone PCam priority, applies the intended zoom/framing/limits, and leaving the zone returns to the default follow camera. |
| Transition | Switching between gameplay, boss, room, or reveal PCams uses the intended tween duration and curve without a visible snap. |
| Shake | Shake is strong enough to sell the impact but does not hide hazards, UI, or player position; temporary shake stops after the event. |
| Cutscene move | Control returns to the gameplay PCam after the authored camera beat, even if the cutscene is skipped or interrupted. |

For platformers, test vertical movement, ledges, and fast horizontal reversals.
For top-down games, test room boundaries, diagonal motion, and camera zones at
doorways. For combat games, test hit shake, boss reveals, and crowded arenas.
For puzzle or exploration games, test static room framing and slow reveal moves.

Do not add a showcase scene that is disconnected from the actual game design.
The pass should confirm the camera behavior the player will experience in normal
play.

## Validation Checklist

Before finishing a generated project that uses Phantom Camera:

- Confirm `addons/phantom_camera/plugin.cfg` exists and the plugin is enabled.
- Confirm every scene has exactly one real `Camera2D` or `Camera3D` per viewport.
- Confirm the `PhantomCameraHost` is below that real camera.
- Confirm the default gameplay PCam starts at a priority above inactive PCams.
- Confirm temporary PCams lower their priority after zones or cutscenes end.
- Run the normal headless build and at least one gameplay test or manual run that
  enters a zone, triggers a transition, and returns to the player camera.
- Record which common camera scenarios were covered, especially any genre-specific
  follow, zone, shake, or cutscene behavior.
