# GodotMaker

**带着你的想法来，交给 GodotMaker，得到一个可运行的 Godot 4 项目。**

GodotMaker 通过 `godotmaker-cli` 把你的游戏想法变成可运行的 Godot 4 项目。它会协助把想法整理成 GDD，然后自动规划、构建、测试、运行、截图、评估和修复，直到当前设计范围完成。结果是本地 Godot 项目，不是托管平台里的黑盒。底层 `/gm-*` 角色命令仍然保留给高级用户。

## 你能得到什么

- **从想法到 GDD** — 用自然语言说清游戏想法，工作流会把它整理成任务、结构、场景和资源需求
- **默认 no-human-in-the-loop** — 一个小型游戏通常需要 3-5 小时 Agent 运行时间，CLI 会持续推进整个循环
- **本地项目归你** — 输出是普通 Godot 项目，可以打开、检查、修改、导出和发布
- **不是封闭平台转卖** — GodotMaker 是源码可见的工作流层，不把项目锁进托管编辑器里转卖 Agent 工作
- **默认带测试** — 单元测试和端到端玩法测试与游戏代码同步生成
- **内置视觉 QA** — 评估器会运行游戏、截图、对照设计检查结果，并把问题送回修复循环
- **源码可见的工作流层** — GodotMaker 的工作流源码以 BUSL 1.1 提供，不把项目锁进托管编辑器或专有运行时

## 从这里开始

1. [安装](wiki/01-getting-started/installation.md) — 必需工具、可选 API key 和环境检查
2. [做你的第一个游戏](wiki/01-getting-started/first-game.md) — CLI 驱动的 idea 到可运行游戏流程
3. [它是怎么工作的](wiki/02-concepts/how-it-works.md) — CLI 背后的角色、质量门禁和修复循环

## 其他快速入口

- [9 个角色](wiki/02-concepts/the-9-roles.md) — 底层角色命令
- [故障排查](wiki/04-troubleshooting/common-problems.md) — 常见问题的解决方法
- [FAQ](wiki/08-reference/faq.md)
- [参与贡献](wiki/07-contributing/development-setup.md)
- [GitHub 仓库](https://github.com/RandallLiuXin/GodotMaker)

## 项目状态

GodotMaker 正在准备源码可见的 public alpha。CLI、视觉 QA 和打包流程还会快速变化；工作流和文档也会继续更新。
