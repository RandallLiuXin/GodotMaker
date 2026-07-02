# GodotMaker Wiki

GodotMaker 把你的游戏想法变成可运行的 Godot 4 原型。正常路径是 `godotmaker-cli`：它会协助把想法整理成 GDD，然后驱动同一套 `/gm-*` 角色命令持续推进规划、实现、测试、运行、截图、评估和修复，直到当前设计范围完成。

## 第一次来？先看这三页

1. [安装](01-getting-started/installation.md) - 必需工具、可选 API key 和环境检查
2. [做你的第一个游戏](01-getting-started/first-game.md) - CLI 驱动的 idea 到原型流程
3. [它是怎么工作的](02-concepts/how-it-works.md) - CLI 背后的角色、质量门禁和修复循环

## Wiki 分区

| 分区 | 什么时候看 |
|------|-----------|
| [快速上手](01-getting-started/installation.md) | 第一次配置 GodotMaker，或新建项目 |
| [核心概念](02-concepts/how-it-works.md) | 想理解 CLI 工作流、9 个角色命令、ECS 和设计选择 |
| [技能系统](03-skills/skill-system.md) | 了解角色技能、辅助技能、审查员技能分别做什么 |
| [故障排查](04-troubleshooting/common-problems.md) | 运行卡住、被拦截或行为异常时，在这里找解法 |
| [工具](05-tools/publish.md) | `publish.py`、`check_env.py`、`check_project.py` 及资源工具参考 |
| [配置](06-configuration/project-config.md) | 每个项目的偏好设置、provider 配置、主机路径、插件版本锁定 |
| [参与贡献](07-contributing/development-setup.md) | 想新增技能、Hook 或工具，或发布版本 |
| [参考](08-reference/glossary.md) | 词汇表、FAQ，以及指向 Changelog 的链接 |

## GodotMaker 能为你做什么

| 能力 | 对你意味着什么 |
|------|--------------|
| **带着想法来，不必先写完整规格** | 用自然语言描述游戏，GodotMaker 会协助整理成 GDD 和规划文档 |
| **让工作流自己推进** | 一个小型原型可能需要 5-8 小时 Agent 运行时间，但你不需要手动驱动每条角色命令 |
| **保留本地 Godot 项目** | 生成的源码、场景、资源、测试、截图和报告都在你的项目文件夹里 |
| **默认带测试** | 单元测试和端到端玩法测试与游戏代码同步生成 |
| **用视觉 QA 形成反馈** | 自动截图和视觉评估会把 UI 与场景问题变成修复任务 |
| **落在成熟引擎上** | 结果是 Godot 项目，可以继续调试、扩展、导出和发布 |

## 当前边界

- GodotMaker 当前面向 2D Godot 游戏，暂不支持 3D 游戏生成。
- 美术管线仍处于 alpha 阶段，图集区域、动画配置或资源绑定有时需要后续 coding agent 修复。
- 像素画风和 TileMap 支持都在计划中，但当前暂不支持。
- 关卡布局、解谜内容和数值平衡仍需要人的判断与手动调整。
- 当前暂不支持音频生成。
- 长时间自动运行对成本敏感，极少数项目也可能在多轮 build/fix/evaluate 后仍无法收敛。

手动 `/gm-*` 角色命令仍然保留给高级用户、调试和框架开发使用，但已经不是推荐的新手首跑路径。正常 CLI 路径支持 Claude Code、Codex 和 OpenCode runner；runner 相关设置见[安装](01-getting-started/installation.md)。

## 项目状态

- 当前版本：见 [`VERSION`](https://github.com/RandallLiuXin/GodotMaker/blob/main/VERSION) 和 [`CHANGELOG.md`](https://github.com/RandallLiuXin/GodotMaker/blob/main/CHANGELOG.md)
- 下一版本计划：[`docs/update/next.md`](../update/next.md)
- 路线图：[`ROADMAP.md`](https://github.com/RandallLiuXin/GodotMaker/blob/main/ROADMAP.md)

## 快速链接

- [GodotMaker 仓库](https://github.com/RandallLiuXin/GodotMaker)
- [gecs - ECS 框架](https://github.com/csprance/gecs)
- [gdUnit4 - 测试框架](https://github.com/MikeSchulze/gdUnit4)
- [godot-mcp - 运行时调试](https://github.com/Coding-Solo/godot-mcp)
