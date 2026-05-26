# Core 技能

Core 技能分为两类：九个以 `/gm-*` 暴露的角色技能，以及十二个由角色技能自动加载的支撑技能。本页对两类技能都有说明。

## 角色技能

共有九个角色技能，每个负责游戏创建的一部分。正常路径下，`godotmaker-cli` 会按顺序驱动它们；手动模式下，你可以按同样顺序运行 `/gm-*` 角色命令，因为每个角色都要求前一个角色已经完成才能开始。

| 命令 | 作用 | 前提条件 | 产出物 |
|------|------|----------|--------|
| `/gm-scaffold` | 创建一个新的 Godot 项目，包含正确的目录结构、所需插件，并完成首次 git 提交 | 无（每个项目只运行一次） | `project.godot`、`addons/`、初始 `CLAUDE.md` 或 `AGENTS.md` |
| `/gm-gdd` | 询问你关于游戏的构想，然后编写设计文档和工作计划 | 已搭建好的项目骨架 | `GDD.md`、`PLAN.md`、`STRUCTURE.md`、`SCENES.md`、`ASSETS.md`、`TOC.md` |
| `/gm-asset` | 生成缺失的美术资源，或分析你提供的美术资源，为构建阶段准备好可用的素材 | `/gm-gdd` 产出的 `ASSETS.md` | `assets/` 下的美术文件，更新后的 `ASSETS.md` |
| `/gm-build` | 通过向 Worker（工人）子 Agent 分批派发任务来实现游戏，Reviewer 会对结果进行审查 | `/gm-gdd` 产出的设计文档 | `src/`、`scenes/` 下的游戏代码，单元测试，端对端测试 |
| `/gm-verify` | 运行机械性检查：项目能否编译、单元测试是否通过、必要文件是否存在 | 已构建好的项目 | 一份打印到聊天里的通过/失败报告，并向 `.godotmaker/stage.jsonl` 追加一个 `verify` 事件 |
| `/gm-evaluate` | 独立运行游戏，截图并对照 GDD 给结果评分 | 已通过验证的项目 | `.godotmaker/evaluation.json`，`e2e/screenshots/` 下的截图 |
| `/gm-fixgap` | 读取评估报告，生成问题列表，并派发 Worker 逐一修复 | `/gm-evaluate` 产出的评估结果 | 更新后的游戏代码，`GAP.md` 归档到 `.godotmaker/gaps/<n>/` |
| `/gm-accept` | 展示当前状态，询问你是接受结果、继续修复，还是停止 | 完整的构建周期 | 接受事件记录到 `.godotmaker/stage.jsonl` |
| `/gm-finalize` | 把当前 tag 的工作文档归档到 `docs/tags/<Tag>/`、本地执行 `git tag <Tag>`、重置每 tag 的运行时状态 | 已接受的构建 | `docs/tags/<Tag>/` 归档、`.godotmaker/final_report.json`、本地 git tag |

`/gm-finalize` 完成后，你可以通过 CLI 开启下一个 tag，也可以手动再次运行 `/gm-gdd`（例如添加新功能）。`/gm-scaffold` 是每个项目只需执行一次的 setup 步骤。

想深入了解每个角色的职责和它做出的各种决策，见 [九个角色](../02-concepts/the-9-roles.md)。

## 支撑技能

支撑技能是角色技能静默加载的参考资料包。你不需要自己调用它们——它们的存在是为了让角色技能在需要时有准确的文档和工具可用。

### 规划类

| 技能 | 提供的内容 | 被谁加载 |
|------|-----------|----------|
| `game-planner` | 设计阶段的访谈结构与 GDD 模板指导，并在定稿前通过 `gdd-auditor` 子 Agent 对当前发布 tag 范围进行独立审计（第一轮必跑，第二轮仅在第一轮发现足够缺口时触发） | `/gm-gdd` |
| `project-scaffold` | 项目目录规则、插件安装步骤、ECS 目录约定 | `/gm-scaffold` |
| `input-mapper` | 管理 `project.godot` 中 Godot 输入动作的参考资料 | `/gm-build`、`/gm-fixgap` |

### Godot 参考类

| 技能 | 提供的内容 | 被谁加载 |
|------|-----------|----------|
| `godot-api` | Godot 4 引擎类文档——方法、属性、信号和枚举 | `/gm-build`、`/gm-fixgap` |
| `gecs` | gecs ECS 插件的 API 参考（Entity、Component、System、World、QueryBuilder） | `/gm-build`、`/gm-fixgap` |

### 构建与运行类

| 技能 | 提供的内容 | 被谁加载 |
|------|-----------|----------|
| `headless-build` | 如何在无窗口（headless）模式下对 Godot 项目进行编译检查 | `/gm-verify`、`/gm-build` |
| `gdunit-driver` | 如何运行 gdUnit4 单元测试并读取结果 | `/gm-verify`、`/gm-build` |
| `godot-e2e` | 如何编写并运行通过网络连接控制实时 Godot 窗口的端对端游戏测试 | `/gm-build`、`/gm-fixgap` |

### 评估类

| 技能 | 提供的内容 | 被谁加载 |
|------|-----------|----------|
| `visual-qa` | 如何分析截图中的视觉缺陷，并与参考图像对比 | `/gm-evaluate` |
| `screenshot` | 如何从运行中的 Godot 实例抓取游戏截图 | `/gm-evaluate`、`/gm-fixgap` |
| `mcp-driver` | 如何在运行时通过 godot-mcp 检查实时 Godot 项目——用于构建工具无法单独诊断问题时 | `/gm-fixgap` |

如果你想查看某个支撑技能的完整参考内容，它的 `SKILL.md` 位于仓库的 `skills/core/<name>/` 目录下。

你不需要直接调用支撑技能——CLI 或上面的角色命令会自动拉取所需内容。
