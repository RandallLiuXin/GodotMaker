# GodotMaker

**带着你的想法来，交给 GodotMaker，得到一个可运行的游戏。**

## 为什么做这个

在游戏开发中，尤其是早期立项/市场验证阶段，一个团队往往会同时提出大于团队人数的idea。之前的做法是通过开发反复讨论最终选定一个idea，然后进行开发验证。结果还常常开发两周后才发现这个idea根本不行，之前的讨论和开发都白费了。因此我开发了 GodotMaker，希望能让单人把想法变成可玩的原型，快速验证想法的可行性和有趣程度。这将极大地加速游戏开发的前期阶段，让开发者更快地找到真正值得投入的游戏创意。

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
2. [做你的第一个游戏](wiki/01-getting-started/first-game.md) — CLI 驱动的 idea 到原型流程
3. [它是怎么工作的](wiki/02-concepts/how-it-works.md) — CLI 背后的角色、质量门禁和修复循环

## 其他快速入口

- [9 个角色](wiki/02-concepts/the-9-roles.md) — 底层角色命令
- [故障排查](wiki/04-troubleshooting/common-problems.md) — 常见问题的解决方法
- [FAQ](wiki/08-reference/faq.md)
- [参与贡献](wiki/07-contributing/development-setup.md)
- [GitHub 仓库](https://github.com/RandallLiuXin/GodotMaker)

## 项目状态

GodotMaker 正在准备源码可见的 public alpha。CLI、视觉 QA 和打包流程还会快速变化；工作流和文档也会继续更新。
