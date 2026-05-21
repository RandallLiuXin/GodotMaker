# 词汇表

GodotMaker 文档和斜线指令输出中常见术语的定义。

---

**Accept** / **Acceptance** — 流水线第八个角色，由 `/gm-accept` 触发。AI 将 **当前 tag** 的成果呈现给你，询问是否封口（继续 `/gm-finalize`）、打回重新修复，或直接停止。你的决定会以 `accept` 事件的形式记录在 `.godotmaker/stage.jsonl` 中。Accept 是按 tag 进行的——同意现在并不意味着整个游戏完成，只是说当前 tag 准备好交付。另见：*Tag*、*Role*。

**Analyst** — 由 `/gm-asset` 派生的子代理，专门分析你提供的图片文件。主代理被阻止直接读取图片（防止原始像素数据耗尽上下文），因此将图片分析委托给 Analyst。Analyst 返回一份艺术风格摘要和可用资源列表。另见：*Sub-agent*。

**Asset** / **ASSETS.md** — "Asset" 指游戏使用的美术或音频文件（精灵、背景、音效）。`ASSETS.md` 是跨 tag 的资源清单，由 `/gm-asset` 维护。

**Component**（ECS）— 附加到实体上的小型纯数据容器。例如 `Health` 组件可能只保存一个数字（`hp: 5`）。组件本身不含任何逻辑。另见：*ECS*、*Entity*、*System*。

**Current role** / `.godotmaker/current_role` — 每个 `/gm-*` 技能作为第一个动作写入的纯文本文件，记录当前激活的角色（如 `build`）。Hook 脚本读取这个文件来决定哪些文件写操作被允许、哪些被阻止。没有 `/gm-*` 技能运行时，文件不存在（或是上一个会话留下的过期记录，`session_start.py` 会将其清除）。另见：*Hook*、*Role*。

**ECS**（Entity-Component-System）— 所有生成的游戏代码遵循的架构。与其把数据和逻辑塞进一个大脚本，ECS 将它们分离：实体只是 ID，组件是挂在实体上的数据袋，系统是每帧遍历匹配实体的函数。这让 AI 生成的代码保持模块化，便于扩展。GodotMaker 使用 [gecs](https://github.com/csprance/gecs) 插件在 Godot 中实现 ECS。另见：*Entity*、*Component*、*System*、*gecs*。

**Entity**（ECS）— 代表游戏世界中一个"事物"（玩家、敌人、子弹）的唯一数字 ID。实体本身没有数据或行为；只有通过附加在它身上的组件才有意义。另见：*ECS*、*Component*。

**Evaluation** / **Evaluator** — 流水线第六个角色，由 `/gm-evaluate` 触发。独立评估当前 tag 是否兑现 `PLAN.md` 的承诺：强制可玩闭环硬门、跑 `e2e/` 套件、对场景截图与参考图做视觉比对。判定结果写入 `.godotmaker/evaluation.json`，输入下一角色 `/gm-fixgap`。另见：*Role*、*Tag*、*Visual QA*。

**Fixgap** / **GAP.md** — 第七个角色，由 `/gm-fixgap` 触发。读取评估报告，创建 `GAP.md` 列出 GDD 描述与游戏当前状态之间的每处差距，然后派发 Worker 逐一解决。修复完成后，`GAP.md` 会归档到 `.godotmaker/gaps/<n>/`。另见：*Role*、*Worker*。

**GDD**（Game Design Document，游戏设计文档）— 描述游戏全部内容的结构化文档（`GDD.md`）。GDD 是跨 tag 的"北极星"——每个 tag 的 `/gm-gdd` 都参考它，必要时也会更新它（被替代的旧设计标记 `(superseded by ...)` 而非删除）。

**gecs** — 提供 Entity、Component、System 基础类的开源 Godot 插件，GodotMaker 在此之上构建。来源：[github.com/csprance/gecs](https://github.com/csprance/gecs)。GodotMaker 在 `config/addon_versions.json` 中锁定具体的插件版本。另见：*ECS*。

**Hook** — Claude Code 在特定事件（会话开始、文件写入前、子代理结束后等）自动运行的小型 Python 脚本。Hook 负责执行流水线规则——例如在 evaluate 角色期间阻止主代理写游戏代码，或在 `/gm-build` 已派发 Worker 但未运行 Verifier 时拒绝结束。Hook 存放在生成项目内的 `.godotmaker/hooks/`。完整列表见 `docs/hooks.md`。

**Milestone** — *Tag* 的旧称，用于 v0.3.0 之前的文档。当前规范术语是 *Tag*；"milestone" 仅残留在归档的 release notes 里（如 `docs/update/v0.2.x.md`）——目前活跃的 hooks、skills、templates 和 wiki 页面都不再使用这个词。

**PLAN.md** — 由 `/gm-gdd` 生成、范围限定为 **当前 tag** 的任务列表。包含 Tag Mechanics（本 tag 要交付的 mechanic 列表）、Inherited Mechanics（先前 tag 已交付、本 tag 必须保持不破坏的 mechanic 列表）、风险任务、主体任务表，每项任务都有状态字段（`pending` / `in_progress` / `completed` / `verified`）。`/gm-build` 通过为每个任务派发 Worker 来逐一推进。Hook `stage_reminder.py` 会阻止 `/gm-build` 在所有任务都标记为 `verified` 之前结束。

**Reviewer** — 一种子代理，以及一套 8 个专项技能（`physics`、`animation`、`ui`、`tilemap`、`navigation`、`shader`、`audio`、`particles`）。当 `PLAN.md` 中所有任务都 `completed` 且 Verifier 通过后，Reviewer 对代码进行检查，比对每个技能的 `gotchas.md` 和 `checklist.md` 中记录的 Godot 特有坑。主 Agent 对每个 finding 做 triage，三选一：ACCEPT（作为新任务追加到 `PLAN.md`）、REJECT（finding 是误报——记录到 `MEMORY.md` 的 **Reviewer Triage Log** 段）或 SKIP（finding 是对的但暂时不修——同段记录）。critical/major 的 REJECT/SKIP 必须附引证。所有 triage 决策都会在 `/gm-accept` 摘要里展示给用户。另见：*Sub-agent*、*Worker*、*Verifier*。

**Rescue** — 由 `/gm-rescue` 触发的主流程外诊断角色。当流水线卡住时调用（通常在多轮 `/gm-fixgap` 都没办法收敛之后）。检查 godotmaker 自身的 hooks、skills、config、templates，判断卡死是否由框架缺陷造成；只输出到聊天（不写文件、不改代码）。如果发现框架缺陷，会起草一份 GitHub issue 草稿供用户审阅后自行提交。隐私：草稿默认不包含项目路径、项目源码、GDD 内容。另见：*Tag*。

**ROADMAP.md** — 项目根目录下的活文档（首次 `/gm-gdd` 运行时生成，后续运行可编辑），按 SemVer 顺序列出所有计划交付的 tag。每个 tag 条目有一行主题 + 若干条 feature。最早一个还没有 `git tag` 的条目就是 **当前 tag**。已有 `git tag` 的条目在本文件中不可修改。

**Role** — GodotMaker 流水线中九个有明确职责的步骤之一，外加一个主流程外的诊断角色 *Rescue*。每个角色对应一条 `/gm-*` 斜线指令，并对可以读写哪些文件有明确的范围限制。九个流水线角色按顺序为：`scaffold`、`gdd`、`asset`、`build`、`verify`、`evaluate`、`fixgap`、`accept`、`finalize`。

**SCENES.md** — 由 `/gm-gdd` 生成的规划文档，列出 **当前 tag** 需要新增或重做的 Godot 场景、包含的内容以及场景之间的关系。先前 tag 的场景描述保留在对应的 `docs/tags/<prev>/SCENES.md` 归档里。

**Skill**（coding-agent 技能）— 一个给所选 coding agent 提供特定工作指令的 Markdown 文件（`SKILL.md`）。GodotMaker 提供 9 个流水线角色技能（Claude Code 使用 `/gm-*`，Codex 使用 `$gm-*`）、辅助技能以及 Reviewer 技能。技能会部署到所选 agent 的项目本地技能目录（Claude Code 为 `.claude/skills/`，Codex 为 `.agents/skills/`）。

**Stage vs Role** — "Stage"是 GodotMaker 早期对流水线步骤的称呼。流水线已被重新设计为基于角色的指令，没有中央协调器。"stage"这个词仍出现在部分文件名中（如 `stage_schemas.json`、`stage.jsonl`），但今后的规范术语是"role"。另见：*Role*。

**stage.jsonl** — 位于 `.godotmaker/stage.jsonl` 的只追加日志文件。每当一个 `/gm-*` 角色成功完成时，它追加一行 JSON：`{"role": "<name>", "ts": "<iso-timestamp>", ...}`（部分事件还带额外字段：`tag`、`decision`、`conclusion`）。Hook 读取此文件决定下一步是否允许进行。`/gm-finalize` 在每个 tag 的最后会清空它。"jsonl"表示每行是一个独立的合法 JSON 对象。

**STRUCTURE.md** — 由 `/gm-gdd` 生成、范围限定为 **当前 tag** 的架构文档：列出本 tag 结束时应有的全部 Components / Systems（含先前 tag 累积的 + 本 tag 新增的或 refactor 的）。

**Sub-agent** — 主角色代理派生的 AI 代理，用于并行处理特定的工作内容。子代理在隔离的 git worktree 中运行，互不干扰。四种子代理类型：*Worker*、*Verifier*、*Reviewer*、*Analyst*。

**System**（ECS）— 每帧遍历所有拥有特定组件组合的实体的函数（或 GDScript 类）。例如，`MovementSystem` 可能遍历所有同时拥有 `Velocity` 组件和 `Position` 组件的实体，每帧更新其位置。System 包含所有游戏逻辑。另见：*ECS*、*Entity*、*Component*。

**Tag** — 一次完整的 `/gm-gdd` → `/gm-finalize` 流水线运行交付一个 **Tag**（采用 SemVer 命名：`v0.1.0`、`v0.2.0`、……）。`/gm-finalize` 完成后会把当前 tag 的工作文档归档到 `docs/tags/<Tag>/` 并在本地执行 `git tag <Tag>`。之后你可以用下一个 `/gm-gdd` 开启下一个 tag，或者就此停在这里。每个 tag 都交付一个最小可玩单元。另见：*ROADMAP.md*。

**TOC.md** — 由 `/gm-gdd` 生成的目录文档，列出所有规划文档及其位置。它提供每个 tag 开始时项目内容的快速概览。

**Verifier** — 运行无头 Godot 构建和 Worker 编写的单元测试，然后报告是否通过的子代理。Verifier 还会执行"对抗性探测"——针对边界情况和错误处理的定向测试。如果验证失败，问题返回给 Worker。另见：*Sub-agent*、*Worker*、*Reviewer*。

**Visual QA** / **VQA** — 将运行中的游戏截图与参考图像或一组书面标准进行比对的过程。`/gm-evaluate` 使用 `visual-qa` 技能，并根据 `vqa_model` 配置选择 `native`、Gemini 或 OpenAI，对照 GDD 描述和 `/gm-asset` 生成的每个场景参考图为场景打分。另见：*Evaluation*。

**Worker** — 实现一个游戏任务的子代理：编写 GDScript 代码、单元测试和端到端测试，然后返回一份结构化报告。Worker 在隔离的 git worktree 中运行。Worker 完成后，必须由 Verifier 和 Reviewer 先后完成验收，才会开始下一个任务。另见：*Sub-agent*、*Verifier*、*Reviewer*、*Worktree*。

**Worktree** — 允许多个工作目录共享同一个仓库的 git 功能。GodotMaker 用 worktree 让并行子代理各自拥有独立的文件夹来写文件，互不冲突。Worktree 要求仓库至少有一个提交，这也是 `/gm-scaffold` 总是创建初始提交的原因。另见：*Sub-agent*。
