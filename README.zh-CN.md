# GodotMaker

[![License: BUSL 1.1](https://img.shields.io/badge/License-BUSL_1.1-orange.svg)](LICENSE)
[![Godot 4.x](https://img.shields.io/badge/Godot-4.x-blue?logo=godotengine)](https://godotengine.org)
[![CI](https://github.com/RandallLiuXin/GodotMaker/actions/workflows/ci.yml/badge.svg)](https://github.com/RandallLiuXin/GodotMaker/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-online-teal)](https://RandallLiuXin.github.io/GodotMaker/zh/)

[English](README.md) | **中文**

> **带着你的想法来，交给 GodotMaker，得到一个可运行的游戏。**

## 为什么需要它

很多工具都在承诺“AI 帮你做游戏”，但真正开始用之后，经常会遇到这些问题：

- 你只是想实现一个想法，却要一直坐在电脑前测试、截图、反馈，让 Agent 一步步改到能用。
- 平台说是在为你实现游戏，但代码和项目留在服务器上，无法完整下载，也无法脱离平台继续开发。
- 好不容易做出一个有趣 demo，却没有落在成熟游戏引擎里，后续迭代、调试、扩展和发布都很困难。
- 本质上只是一个开发工作流，却在中间转卖高价 token，把你锁进他们的计费和运行环境。

GodotMaker 选择另一条路：你带着游戏想法来，它协助你整理成 GDD，然后自动驱动 Agent 完成规划、实现、测试、运行、截图评估和修复。几个小时后，你验收的是一个真正落在本地的 Godot 项目。

项目代码在你手里，框架工作流源码可用、本地优先，并可在 Business Source License 允许的范围内免费运行。想继续打磨，就继续完善想法或 GDD，再跑下一轮。

## 它有什么不同

- **默认 no-human-in-the-loop。** 类似 coding agent 的 long-running goal/task 模式，说清目标后让它自主持续推进。
- **自然语言到完整游戏项目。** 输入可以从一个游戏想法开始，GodotMaker 会协助把它整理成设计契约。
- **代码属于你。** 输出是普通 Godot 项目：源码、场景、资源、测试、截图、报告都在本地。
- **通过设计持续迭代。** 不是一次性生成后结束，而是可以不断完善想法或 GDD、不断提升游戏效果。
- **基于成熟引擎。** 结果落在 Godot 生态里，可以继续调试、扩展、导出和发布。
- **没有中间商赚差价。** GodotMaker 是工作流层，不通过封闭平台转卖 agent 工作。
- **源码可见的自动化流程。** 框架公开可查看，可在许可范围内运行、修改和贡献。
- **GodotMaker CLI驱动。** 提供命令行工具，方便你更好的全自动化的使用 GodotMaker 工作流。

Claude Code、Codex、Gemini、OpenAI、xAI、Tripo 等外部 runtime 或模型 provider 可能有自己的价格、额度和数据政策。GodotMaker 保证的是框架工作流源码可用、项目本地、产物归你。

## Agent 会做什么

一次运行中，GodotMaker Agent 会持续把设计往前推进：

- 把你的想法整理成 `GDD.md`、任务、场景、系统和验收标准
- 在 Godot 中实现玩法
- 写代码的同时编写 gdUnit4 单元测试
- 编写像玩家一样操作游戏的端到端测试
- 运行游戏并截图
- 对照 GDD 检查结果
- 把缺失玩法、UI 问题、视觉问题送回修复循环

一个小型游戏通常需要 **3-5 小时的 Agent 运行时间**。不过你不需要手动驱动每个阶段，也不需要一直守在电脑前，工作流会自己持续推进。

## 快速开始

```bash
npm install -g godotmaker-cli

mkdir my-game
cd my-game

# 带着你的游戏想法，然后运行：
godotmaker
```

CLI 会从 idea 梳理和 GDD 规划开始驱动工作流，直到生成一个可玩的 Godot tag。高级用户仍然可以直接在 Claude Code 中运行 `/gm-*`，或在 Codex 中运行 `$gm-*`。

如果你要开发 GodotMaker 框架本身：

```bash
git clone https://github.com/RandallLiuXin/GodotMaker.git
cd GodotMaker
pip install -r tools/requirements.txt
python tools/check_env.py
```

## 你需要准备

| 工具 | 用途 |
|---|---|
| [Godot 4.5+](https://godotengine.org) | 运行生成出的游戏 |
| [Claude Code](https://claude.ai/code) 或 [Codex](https://openai.com/codex/) | Agent runtime |
| Node.js 18+ | 运行 `godotmaker-cli` 和 Godot MCP 工具 |
| Python 3.10+ | 运行 GodotMaker 辅助脚本 |
| Git 2.30+ | 提供本地历史和 Agent worktree |

只有当项目配置选择 API provider 时，才需要设置对应 API key。native 图片或视觉路径可以使用你选择的 Agent runtime。

## 了解更多

- [安装](https://RandallLiuXin.github.io/GodotMaker/zh/wiki/01-getting-started/installation/)
- [你的第一款游戏](https://RandallLiuXin.github.io/GodotMaker/zh/wiki/01-getting-started/first-game/)
- [工作原理](https://RandallLiuXin.github.io/GodotMaker/zh/wiki/02-concepts/how-it-works/)
- [常见问题](https://RandallLiuXin.github.io/GodotMaker/zh/wiki/04-troubleshooting/common-problems/)
- [路线图](ROADMAP.md)
- [完整文档](https://RandallLiuXin.github.io/GodotMaker/zh/)

## 状态

GodotMaker 正在准备源码可见的 public alpha。CLI、Codex 支持、视觉 QA 和打包流程还会快速迭代。

抢鲜体验功能和建议备选方案：

| 范围 | 当前状态 | 如果你更在意稳定可控 |
|---|---|---|
| Codex runner | 预览功能。它适合尝试 native 生图和 Codex 驱动的运行，但这条路径仍比 Claude Code 工作流更新。 | 主流程优先使用 Claude Code。 |
| 美术生产线 | 预览功能。当前流程可以生成参考图、角色 canonical source、动作 source sheet、UI sheet 和运行时素材草图，但角色、动画、UI 组件、UI 动效和视觉一致性仍需要人工审查，也可能需要手动替换。 | 把你自己准备的视觉资源放到 `assets/` 下，然后运行 `/gm-asset`，让工作流分析这些资源、更新 `assets/manifest.json`，并把匹配的 `ASSETS.md` 行标记为 `provided`。 |
| 3D 游戏 | 当前 pipeline 暂不支持。工作流目前主要面向 2D 游戏。 | 现阶段优先制作 2D 游戏，或在生成后手动补充 3D 内容。 |
| 音频生成 | 当前 pipeline 暂不支持。音频资源会被视为用户提供或延期。 | 手动准备音乐和音效，并在音频工作流完成前自行接入项目。 |

后续计划提供专门的美术资源制作 UI，让筛选、裁剪、替换和审查更可靠。

如果你觉得这个方向有价值，欢迎 star、试用 CLI，并把你希望它做得更好的游戏类型和问题提到 issue。

## 运行时说明

GodotMaker 本身是一个工作流层，实际执行依赖外部 Agent runtime。这些 Agent 不是本仓库维护的组件，长时间自动化运行时偶尔会遇到运行时自身的小问题，例如静默超时、非输出式自动化任务已经完成但进程没有主动退出、临时工具失败、速率限制，或子进程需要额外清理。

绝大多数一次性的 Agent 失败都可以通过停止当前运行、重新启动 `godotmaker-cli` 恢复；工作流会根据本地项目状态继续推进。我们非常欢迎提交 feedback 和 issue，如果能附上当次运行的必要信息和项目里的 `.godotmaker/` 目录就更好了。

## 许可证

Business Source License 1.1。见 [LICENSE](LICENSE)。每个发布版本会在首次公开发布 4 年后自动转为 Apache License 2.0。**用 GodotMaker 做出来的游戏完全归属于你**，但仍需遵守第三方引擎、素材、模型 provider、runtime 或依赖项可能适用的条款。
