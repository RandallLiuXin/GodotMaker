# 技能系统

在 Claude Code 里，"技能"（Skill）是一组为特定任务打包好的指令和参考文档。你可以把每个技能想象成一本专科手册：当 Claude 需要完成某件事——搭建项目骨架、编写游戏逻辑、排查常见 bug——它就会找到对应的技能，按照里面的指引来操作。GodotMaker 的技能分为两层。

## 第一层 — Core 技能

Core 技能是驱动整个游戏创建流程的引擎，分为两类：

**角色技能（Role skills）** 是框架暴露的九个 `/gm-*` 命令。每个命令负责制作游戏的一部分——设计、构建、测试等等。正常路径下，`godotmaker-cli` 会替你按顺序驱动它们；高级用户仍然可以直接运行这些角色命令。完整的命令列表见 [Core 技能](core-skills.md)。

**支撑技能（Supporting skills）** 是角色技能在后台静默加载的参考资料包，包含 Godot API 文档、ECS 框架参考手册，以及运行测试的辅助工具。你不需要自己调用它们——它们的存在是为了让角色技能在工作时有准确、及时的信息可以依赖。支撑技能同样在 [Core 技能](core-skills.md) 中有说明。

## 第二层 — Reviewer 技能

Reviewer（审查员）技能是八个专项领域清单，覆盖物理、UI、音频、动画等方向。它们不是斜杠命令——你不会直接输入它们。相反，一个 Reviewer 子 Agent（自动启动的独立 Claude 实例）会在 `/gm-build` 和 `/gm-fixgap` 期间加载相关的 Reviewer 技能，对刚写好的代码逐条核对已知的 Godot 坑点，并汇报发现的问题。

完整列表以及每个 Reviewer 能捕获哪类问题，见 [Reviewer 技能](reviewer-skills.md)。

## 技能是如何部署的

技能文件存放在本仓库的 `skills/core/`、`skills/reviewer/` 和 `skills/assets/` 目录下。当你运行 `python tools/publish.py <project>` 时，每个非私有的技能目录都会被复制到 `<project>/.claude/skills/`，Claude Code 会自动找到它们。运行 `python tools/publish.py --agent codex <project>` 时，publish 会把同一套技能写入 `<project>/.agents/skills/`，并附带 Codex runtime mapping references，让 Codex 能解释 `.claude/...` 路径和 `/gm-*` 命令这类 Claude-first 表面语义。Asset 的 `_shared` 不是可调用的 Skill；它会以 schema、compiler registry 和 L0-L4 validator 运行时的形式发布到 `<project>/.godotmaker/asset-runtime/`。

被多个技能共用的参考文档（例如 Worker 调度协议）在 `skills/core/_shared/` 中保存唯一的权威副本。发布步骤会把每份共享文件部署到每个使用方技能的 `references/` 文件夹里。如果你在为 GodotMaker 做贡献并需要修改共享文档，请始终编辑 `_shared/` 下的源文件——部署出去的副本是自动生成的，下次发布时会被覆盖。

## 延伸阅读

- [Core 技能](core-skills.md) — 九个角色命令与十二个支撑技能
- [Reviewer 技能](reviewer-skills.md) — 八个专项质量审查技能
