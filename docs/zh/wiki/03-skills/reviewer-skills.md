# Reviewer 技能

Reviewer（审查员）技能是领域专家，专门捕捉生成代码中 Godot 特有的错误。Godot 有很多微妙的规则——物理回调不能修改游戏状态、UI 容器会无视手动设置的位置、音频流在内存中占用的空间远超文件大小——AI 在编写游戏代码时偶尔会踩到这些坑。Reviewer 技能的作用就是在这些错误进入你的项目之前把它们揪出来。

一个 Reviewer 子 Agent（自动运行的独立 Claude 实例）会在 `/gm-build` 和 `/gm-fixgap` 期间，根据刚写好的代码涉及哪些 Godot 系统，加载相关的 Reviewer 技能。它读取代码、对照技能中记录的已知坑点逐项核查，并生成一份报告。这一切都不需要你手动触发。

## 八个 Reviewer 技能

| 技能 | 覆盖范围 | 典型问题示例 |
|------|---------|-------------|
| `physics` | 碰撞检测、物理体、碰撞层、物理回调 | 在 `body_entered` 回调中直接调用 `queue_free()`——Godot 在碰撞事件期间会锁定物理空间，所有修改状态的操作都必须延迟执行 |
| `animation` | AnimationPlayer、AnimationTree、AnimatedSprite2D、状态机 | 在 `AnimationTree.active = true` 时调用 `AnimationPlayer.play()`——AnimationTree 每帧都会覆写它所追踪的所有属性，导致直接播放调用毫无可见效果 |
| `ui` | Control 节点、容器、布局、焦点、鼠标输入、主题 | 给 Container 的子节点设置 `position` 或 `scale`——容器会完全接管子节点的变换，任何手动设置的位置都会被覆盖 |
| `tilemap` | TileMapLayer、TileSet、地形绘制、瓦片碰撞 | 调用 `get_cell_tile_data()` 后修改返回值——它返回的是共享引用，修改一个格子的数据会悄悄改变所有使用同一瓦片类型的格子 |
| `navigation` | NavigationAgent、寻路、规避、导航网格烘焙 | 在 `_ready()` 中直接设置 `target_position`——NavigationServer 要等到第一个物理帧之后才会完成区域数据同步，在此之前的任何查询都会返回空路径 |
| `shader` | ShaderMaterial、GLSL uniform、屏幕纹理、材质共享 | 给期望 float 类型的 shader uniform 传入整数——Godot 从脚本设置 uniform 时不校验类型，类型不匹配会静默失败，shader 会沿用默认值 |
| `audio` | AudioStreamPlayer、音频总线、复音、音频流生命周期 | 启动时预加载大量压缩 OGG 文件——压缩音频文件在运行时会被解码为原始 PCM 数据存入内存，一个 5 MB 的 OGG 可能消耗约 50 MB 的 RAM |
| `particles` | GPUParticles、CPUParticles、拖尾、子发射器、碰撞 | 在运行时修改粒子节点的 `amount` 属性——引擎会在该变更时重新分配整个粒子缓冲区，导致当前所有可见粒子瞬间消失 |

## Reviewer 技能的文件结构

每个 Reviewer 技能位于 `skills/reviewer/<name>/`，包含三个文件：

- `SKILL.md` — 入口文件：说明何时应用本技能、哪些代码模式会触发审查，以及整体审查流程。
- `gotchas.md` — 知识库：按编号列出 Godot 引擎的具体坑点，每条包含症状、根本原因和正确的修复方式。这些是"会出问题的地方"。
- `checklist.md` — 操作清单：Reviewer 对代码逐项执行的具体检查，每项都对应 gotchas.md 中的特定坑点。例如，检查项 S1 对应的是坑点 G1 描述的模式。

Reviewer 子 Agent 读取这三个文件，并生成一份结构化报告，用坑点 ID 标注发现的每个问题（例如："physics G1：在 `body_entered` 中直接调用 `queue_free()`"）。

## Reviewer 发现问题后怎么办

主 Agent 对每个 finding 做 triage，三选一：ACCEPT（追加新任务到 `PLAN.md`，由下一批 Worker 修复）、REJECT（finding 是误报）或 SKIP（finding 是对的但暂时不修）。不确定时默认值：critical/major → ACCEPT；minor → SKIP。critical/major 的 REJECT 或 SKIP 必须附引证（gotcha 条目、API 文档、过往架构决策或项目约束、现有任务 ID）。minor 不需要引证。原始 finding 和 triage 决策不写入 `MEMORY.md`。

循环持续到上一次 review 没有任何 ACCEPT 为止。

值得注意的是，这一步不能被悄悄跳过。一个名为 `check_completion.py` 的钩子脚本会在 `/gm-build` 或 `/gm-fixgap` 尝试结束会话时运行。如果 Worker 跑过了但 Verifier（验证员）和 Reviewer 没有跑，钩子会阻止会话结束。质量检查是强制要求，不是可选项。
