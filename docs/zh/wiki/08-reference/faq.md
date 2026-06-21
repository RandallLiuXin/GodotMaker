# 常见问题

---

## 入门

### 我需要懂游戏开发吗？

不需要。GodotMaker 专为有游戏想法但不是游戏开发者的人设计。你用白话描述自己想要什么，在设计展示给你时确认感觉对不对，然后让 AI 去实现。不过，你需要阅读生成的 `GDD.md`，并确认它是否准确表达了你的意图——AI 来写，但你来拍板。

### 我需要付费 API key 吗？

只有当项目配置选择 API 后端时才需要对应 key。runtime-native 图片生成或 VQA 取决于你选择的 Agent runtime；OpenCode 项目应配置为 `codex` 或 API 后端图片/VQA provider。`gemini:<model>` 需要 `GOOGLE_API_KEY` 或 `GEMINI_API_KEY`，`openai:<model>` 需要 `OPENAI_API_KEY`，`grok:<model>` 需要 `XAI_API_KEY`。

Claude Code 本身需要 Anthropic 账号并开通 API 访问（或已开通 Claude Code 的 Claude Pro / Team 订阅）。

详细配置步骤见安装页面。

### 我需要哪个版本的 Godot？

Godot 4.5 或更高版本。GodotMaker 不支持 Godot 3.x 或 Godot 4.3 及以下版本。

### 做一个游戏要多长时间？

对于一个小游戏，通常需要 **5-8 小时 Agent 运行时间**。你自己的注意力主要花在前期澄清想法，以及结束后验收结果。设计清楚后，`godotmaker-cli` 会驱动同一套 `/gm-*` 角色完成规划、构建、验证、评估、截图和修复，而不是让你手动触发每条命令。游戏越复杂，`PLAN.md` 中的任务数越多，时间也相应增加。

### 我可以用 C# 代替 GDScript 吗？

可以。GodotMaker 同时支持 GDScript 和 C#。ECS 组件和系统可以用任一语言编写。使用 C# 时，请确保你使用的是支持 .NET 的 Godot 构建版本。

---

## 流水线行为

### 什么是 tag？

一个 **tag** 是一次完整的流水线通关：`/gm-gdd`、`/gm-asset`、`/gm-build`、`/gm-verify`、`/gm-evaluate`、必要时 `/gm-fixgap`、`/gm-accept`、`/gm-finalize`。Tag 采用 SemVer 命名——第一个 tag 永远是 `v0.1.0`，必须交付可玩闭环；后续每个 tag 添加一组功能或重构已有系统。`ROADMAP.md` 列出计划中的所有 tag，最早一个还没有 `git tag` 的就是当前 tag。正常运行时由 CLI 驱动这个流程；高级用户仍然可以手动用 `/gm-gdd` 开启下一个 tag。`/gm-scaffold` 每个项目只运行一次，不在 tag 之间重复。

### 如果我想中途停下来怎么办？

随时可以停。下次打开项目时，GodotMaker 会读取 `.godotmaker/stage.jsonl` 来确认你上次到哪一步。正常 CLI 路径下，再次运行 `godotmaker-cli` 即可恢复；手动角色命令模式下，再次运行同一个 `/gm-*` 角色即可从中断处继续。

详细的恢复场景说明见 [恢复与续跑](../04-troubleshooting/recovery-and-resume.md)。

### 我可以同时运行两个角色吗？

不行。每个角色启动时会将自己的名字写入 `.godotmaker/current_role`，Hook 脚本利用这个文件执行写权限控制。如果第二个角色在第一个还在运行时尝试启动，文件权限 Hook 会立刻开始拦截意外的写操作。让 CLI 管理顺序即可；如果手动运行角色，请一次只运行一个，等它完成再开始下一个。

### 为什么有些指令可以重复运行，有些不行？

`/gm-scaffold` 是每个项目只执行一次的命令——在已有项目上重跑会覆盖项目设置。`/gm-asset` 在 tag 内可以随时重跑，有新资源需求时使用。从 `/gm-build` 开始的命令遵循 per-tag 周期：应按顺序运行，重跑某个命令会重做当前 tag 的那个阶段。手动模式下，`/gm-gdd` 会开启一个新的 tag。

### `/gm-build` 内部做了什么？

`/gm-build` 推进 `PLAN.md` 中的任务列表：先派 **Worker** 把所有任务做到 `completed`，然后跑一次 verify+review pass——**Verifier** 无头编译项目并运行测试，**Reviewer** 检查 Godot 特有的坑。主 Agent 对每个 finding 做 triage，三选一：ACCEPT（作为新任务加到 `PLAN.md`）、REJECT（finding 是误报——记录到 `MEMORY.md` 的 **Reviewer Triage Log** 段）或 SKIP（finding 是对的但暂时不修——同段记录）。critical/major 的 REJECT/SKIP 必须附引证；这些决策都会在 `/gm-accept` 或 final review 摘要里展示。循环持续到没有任何 ACCEPT。如果 Worker 跑过了但 Verifier 或 Reviewer 没跑，`check_completion.py` Hook 会拒绝 `/gm-build` 结束。

### AI 为什么需要 git worktree？

当 `/gm-build` 并行运行多个 Worker 时，每个 Worker 需要独立的文件夹来写文件，互不冲突。Git worktree 允许多个工作目录共享同一个仓库历史。这也是 `/gm-scaffold` 要创建初始 git 提交的原因——worktree 需要至少一个提交才能使用。

---

## 质量与输出

### 为什么我的游戏和 GDD 里说的不完全一样？

AI 代码生成不是确定性的，游戏系统之间复杂的交互可能产生预期之外的结果。这正是 `/gm-evaluate` 和 `/gm-fixgap` 存在的原因：评估器对照你的 GDD 给运行中的游戏打分，生成差距列表，然后 Fixgap 派发 Worker 逐一填补。对于小游戏，跑一轮通常就够了；更复杂的游戏可能需要再跑一轮。

### 我可以手动修改生成的代码吗？

可以，你的修改会被保留。但要注意，如果你在新 tag 中再次运行 `/gm-build`，它可能会添加涉及同一文件的新任务——新的 Worker 输出可能会扩展或部分覆盖你的手动修改。建议手动修改保持在小范围内，并在 `MEMORY.md` 中记录下来，让 AI 知道这些改动是有意为之的。

### 截图和测试结果在哪里？

- 每个场景的视觉参考图（由 `/gm-asset` 生成）：`references/scene_<name>.png`
- 评估期间截取的运行时截图：`e2e/screenshots/`
- 动画帧序列（每个场景一个子目录）：`e2e/screenshots/scene_<name>/frame_*.png`
- 每轮评估归档的截图和判定：`.godotmaker/evaluation-runs/`
- 评估分数和差距列表：`.godotmaker/evaluation.json`
- Hook 和流水线指标：`.godotmaker/metrics_current.jsonl`

### 为什么用 ECS 而不是普通的 Godot 脚本？

普通的 Godot 节点脚本往往把数据、逻辑和场景结构混在一个文件里。随着游戏规模增长，这些文件越来越难改——动一个地方就可能破坏另一个地方。ECS 干净地分离了关注点：数据在组件里，逻辑在系统里，实体只是连接两者的 ID。对于 AI 生成的代码，这一点尤为重要——新行为永远是新组件加新系统，而不是去修改一个已有的千行脚本。

更详细的解释见 [用大白话讲 ECS](../02-concepts/ecs-in-plain-english.md)。

### 我怎么知道构建是否成功？

`/gm-verify` 完成后，会按检查项把通过/失败报告打印出来——整体通过时还会向 `.godotmaker/stage.jsonl` 追加一个 `verify` 事件。`/gm-build` 期间每个 Worker 的报告也记录了其测试是否通过。如果 Godot 无头构建失败或单元测试失败，验证会报告失败，并按情况把工作流送回 build 或 fixgap。

---

## 费用与隐私

### 我的游戏数据去哪了？

所有游戏文件都在你自己的机器上。AI 调用会发送给当前智能体运行时使用的模型服务商。API 后端图片生成会发送给 `asset_image_model` 选择的提供方（Gemini、OpenAI 或 xAI）；`native` 图片生成由当前运行时处理，`codex` 图片生成由 Codex 处理。GodotMaker 没有自己的服务器，因此不会把游戏内容存储到 GodotMaker 服务器上。

### 我的游戏项目属于我吗？

是的。GodotMaker 只是把文件部署到你的文件夹里，然后由 AI 填充内容。用 GodotMaker 创建的游戏、项目源码、素材、截图、报告、导出产物和其他输出都不是 GodotMaker，本身归你所有。GodotMaker 框架本身以自己的源码可见许可证发布，但你的游戏内容和代码属于你；你仍需遵守第三方引擎、素材、模型 provider、runtime 或依赖项可能适用的条款。

---

## 故障排查

### 有个 Hook 一直在拦截我，没法继续。

Hook 内置了防死锁限制。`check_completion.py` 最多允许连续拦截 5 次后强制放行；`check_worker_report.py` 每个子代理最多允许 2 次拦截。如果你反复碰到这个上限，说明流水线某处出了问题——检查失败子代理的报告，看看是否有缺失的部分或格式错误的输出。

常见 Hook 报错及解读方法见 [常见问题](../04-troubleshooting/common-problems.md)。

### Worker 启动时出现 "fatal: not a valid object name: HEAD"。

这说明项目还没有 git 提交。`/gm-scaffold` 应该已经创建了一个。请通过 CLI 或手动命令重新运行 setup/scaffold，或手动创建初始提交：`git commit --allow-empty -m "init"`。

### 我的评估分数很低，但游戏看起来没问题。

评估器对照每个场景的参考图和 GDD 描述进行视觉 QA。如果 `/gm-asset` 没有生成 `references/scene_*.png` 文件，评估器就没有视觉参考来比对，会给出保守的低分。在重新评估前，先重新运行 asset 命令补全缺失的参考图。

### 我怎么回滚到旧版本的 GodotMaker？

在 GodotMaker 仓库中切换到旧版本标签，然后带 `--force` 重新发布：

```bash
git checkout v0.1.0          # 在 GodotMaker 仓库中执行
python tools/publish.py --force /path/to/my-game
```

`--force` 同时做几件事：跳过 MINOR/MAJOR 升级提示、允许降级；对 Claude Code 目标还会覆盖 `.claude/settings.json`。完整的干净重新初始化（清空所选 agent 的 skills、`.godotmaker/hooks/`、运行时状态文件等）**只在 MAJOR 升级时**触发——PATCH/MINOR/SAME 升级时只是原地覆盖现有框架文件。所以在上面的降级例子里，`--force` 的主要作用是绕过降级阻拦。

### 流水线里提到 "stage" 或 "role"，这是怎么回事？

"Stage" 是 GodotMaker 早期对流水线步骤的称呼。框架现在暴露 `/gm-build` 这类 role-based command，`godotmaker-cli` 可以在正常运行中驱动这些角色。部分文件名（如 `stage.jsonl` 和 `stage_schemas.json`）为了延续性仍沿用旧名称。在工具输出或旧文档中看到 "stage" 时，把它当作 "role" 的同义词就好。另见词汇表中的 *Stage vs Role*。
