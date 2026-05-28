# 9 个流水线角色 + 1 个诊断角色

每个角色对应一条你在 Claude Code 里输入的斜杠命令。9 个流水线角色按顺序执行——如果跳过了某个前置步骤，系统会告诉你。第 10 个角色 `/gm-rescue` 在主流程之外，只在卡住时调用。

流水线 **按 tag 运行**（SemVer：v0.1.0、v0.2.0、……）。一次完整的 `/gm-gdd → /gm-finalize` 流程交付一个 tag。`/gm-scaffold` 在项目最开始只运行一次。`/gm-finalize` 关闭一个 tag 之后，可以再来一次 `/gm-gdd` 开启下一个 tag。

`ROADMAP.md` 列出项目计划的所有 tag；最早一个还没有 `git tag` 的条目就是 **当前 tag**。

---

## `/gm-scaffold`

**做什么：** 创建一个空的 Godot 项目，建好正确的目录结构，安装必需的插件（`gecs` 提供 ECS 支持，`gdUnit4` 提供测试支持），并提交第一个 git commit。

**什么时候运行：** 在一切开始之前，只运行一次。项目目录必须已存在但是空的（或者只有一个 `.git` 文件夹）。

**背后发生了什么：**
- 写入 `project.godot`、`addons/`、`src/`、`scenes/`、`assets/`、`e2e/`、`test/`
- 安装并配置 `gecs` 和 `gdUnit4`
- 创建 `e2e/conftest.py`（测试框架入口）

**你得到什么：** 一个干净、可运行的 Godot 项目，还没有任何游戏逻辑。

**需要知道的：** 这条命令每个项目只运行一次。在同一个项目里再次运行会提前中止并给出说明。

---

## `/gm-gdd`

**做什么：** 规划 **当前 tag**。根据 `ROADMAP.md` 是否已存在自动选择两种模式之一：

- **首次模式**（还没有 `ROADMAP.md`）：对整个游戏进行完整的 Socratic 访谈 → 生成 `GDD.md` → 推导出 `ROADMAP.md`（按 SemVer 拆分为多个 release tag）→ 让你确认 roadmap → 生成 v0.1.0 的工作文档。
- **后续模式**（已有 `ROADMAP.md`）：聚焦当前 tag 的 roadmap 条目 → 询问你是要保持、调整还是改写设计 → 可选地更新 `GDD.md`（被替代的旧设计标记 `(superseded by ...)` 而非删除）和 `ROADMAP.md` → 生成当前 tag 的工作文档（如果设计与已交付的 tag 矛盾，会显式生成 refactor 任务）。

**什么时候运行：** 在 `/gm-scaffold` 之后（首个 tag），或者在 `/gm-finalize` 之后（每个后续 tag）。

**你得到什么：**
- 跨 tag（root 累积）：`GDD.md`、`ROADMAP.md`，以及向 `ASSETS.md` 追加的新行
- 当前 tag（root，本轮覆写）：`PLAN.md`（带 `**Tag:**` header、Tag Mechanics 列表、Inherited Mechanics 列表）、`STRUCTURE.md`、`SCENES.md`、`TOC.md`

**需要知道的：** 访谈中要尽量具体——"俯视角僵尸射击，波次刷怪 + 高分榜"远比"一个僵尸游戏"有用。Roadmap 确认是强制门：没确认就没法继续生成产出。`/gm-asset` 之前你可以自己编辑这些文档。

---

## `/gm-asset`

**做什么：** 填充本 tag 引入的新资源（只处理本 tag 新增的行；先前 tag 的行在这里是不可变的）。

**什么时候运行：** 在 `/gm-gdd` 之后、`/gm-build` 之前。tag 期间任何时候添加了新美术都可以再跑。

**背后发生了什么：**
- 读取 `ASSETS.md` 中本 tag 的 MISSING 行
- 对你已经提供的资源：派 Analyst 子代理检查图片文件、记录其内容
- 对仍缺失的资源：通过图像生成 API 自动生成（Gemini 或 xAI，取决于你的配置）
- 对 `SCENES.md` 中的每个场景：根据场景描述、艺术方向和你提供的素材风格，生成场景目标参考图，写入 `references/scene_<name>.png`
- 用实际文件路径和最终状态更新 `ASSETS.md`

**你得到什么：** `assets/` 目录里的美术文件、`references/` 目录里的场景参考图，以及本 tag 新增行被标记为 `provided` / `generated` / `deferred`。这些场景参考图会成为视觉合约，后续 `/gm-evaluate` 用它们来对照运行时截图。

**需要知道的：** 如果先前 tag 的资源坏了，作为 `/gm-fixgap` 修复任务提出。

---

## `/gm-build`

**做什么：** 通过协调一组专门的辅助 Agent，实现 **当前 tag** 的范围——所有的 GDScript 代码、场景和单元测试。

**什么时候运行：** 在 `/gm-asset` 之后。当前 tag 必须已完成 `/gm-gdd`。

**背后发生了什么：**
- 恢复阶段：如果 `.godotmaker/verify_report.json` 中存在上一次 `/gm-verify` 留下的新鲜失败报告，把每个 check 的失败翻译成 `pending` 任务追加到当前 tag 的 `PLAN.md`，再继续后续流程
- 读取当前 tag 的 `PLAN.md`，找出待处理的任务，从风险最高的开始
- 派遣 Worker（最多同时 3 个）——每个 Worker 实现一个游戏系统及其单元测试，完成后汇报
- `PLAN.md` 中所有任务都达到 `completed` 后，派遣一个 Verifier（无界面编译并跑单元测试），然后派遣一个 Reviewer（拥有 Godot 特有的领域知识——物理、UI、动画等）——每个循环迭代一次 verify+review pass，不再按 Worker 数量触发
- 对每个评审 finding，主 Agent 在三个选项中选一个：ACCEPT（在 `PLAN.md` 追加新的修复任务）、REJECT（finding 是误报——记录到 `MEMORY.md` 的 **Reviewer Triage Log** 段）、SKIP（finding 是对的但暂时不修——同段记录）。默认值：critical/major → ACCEPT；minor → SKIP。critical/major 的 REJECT/SKIP 需附强制引证（gotcha 条目、API 文档、过往决策或任务 ID）
- 只要本轮有任何 finding 被 ACCEPT，循环就回到派遣 Worker 阶段
- 只有当 `PLAN.md` 里所有任务都标记为 `verified`，且最后一轮评审 ACCEPT 数为零，构建才结束

**你得到什么：** `src/` 里的游戏代码、`scenes/` 里的场景、`test/` 里的单元测试——全部限定在本 tag 的新增 / refactor 范围内。

**需要知道的：** 在这个步骤里你无法自己写游戏代码——权限系统会阻止。主 Agent 负责协调，Worker 负责实际写代码。Worker 触动当前 tag 范围之外的文件，必须 `PLAN.md` 中有显式 refactor 任务点名那些文件；不允许"顺手清理"。如果同一个任务失败三次，构建会暂停并询问你下一步怎么做。

---

## `/gm-verify`

**做什么：** 对整个项目做一次快速的机械检查——编译、单元测试、Lint、文件结构。Tag 无关——总是针对当前状态运行，不区分你在哪个 tag。

**什么时候运行：** 在 `/gm-build` 之后，以及每次 `/gm-fixgap` 之后。

**背后发生了什么：**
- 无界面运行 Godot 构建，检查编译错误
- 通过 `gdUnit4` 运行 `test/` 里的所有单元测试
- 通过 `tools/check_project.py` 跑静态项目检查（build/ecs/tests/plan/mcp 五项；e2e 检查归 Evaluator 阶段）
- 把结构化结论写入 `.godotmaker/verify_report.json`（每次都写，无论 PASS 还是 FAIL）

**你得到什么：** 两份产出——一份给人看的对话内验证报告，以及 `.godotmaker/verify_report.json` 同等信息的结构化版本。全部通过时，`/gm-verify` 还会向 `.godotmaker/stage.jsonl` 追加一个 `verify` 事件。

**需要知道的：** `verify_report.json` 是协议级别的反馈通道——下一步的 `/gm-build` 或 `/gm-fixgap` 读它，把失败翻译成待办任务，而不是盲目重试。每个 check 的 `result` 是 `pass | warn | fail | error` 四选一：`fail` = 项目代码有问题（修代码）；`error` = 验证工具自身崩了，修法是改 lint/测试配置（`tooling_notes` 里给出），不要删项目代码。schema 和消费规则文档化在 `gm-verify/SKILL.md`。`/gm-verify` 不强制 tag 相关的 E2E 或回归——那是 `/gm-evaluate` 的职责。如果 `/gm-verify` 失败：构建中回 `/gm-build`，评估之后回 `/gm-fixgap`——两者都会自动读取这份报告。

---

## `/gm-evaluate`

**做什么：** 独立评估 **当前 tag** 是否兑现了它的 `PLAN.md` 承诺，以及来自先前 tag 的、仍在支持的所有 mechanic 是否都还能跑。

**什么时候运行：** 在 `/gm-verify` 通过之后。

**背后发生了什么：**
- 读取当前 tag 的 `PLAN.md` 中的 Tag Mechanics + Inherited Mechanics——对构建过程一无所知
- 维护一份单一的 `e2e/` 目录，让它始终反映当前游戏：为本 tag 新增的 Tag Mechanic 写新测试，确认继承的 mechanic 测试还在，对 PLAN 中 Main Build refactor 任务显式删除的 mechanic 同步删除其测试
- 强制 **可玩闭环硬门**：headless 启动不崩 + 至少一个 mechanic 能跑通 E2E + 至少一个 {死亡/胜利/退出} 出口可达
- 跑完整套 `e2e/`——每个仍在支持的 mechanic 都要测试。继承 mechanic 的失败和新 mechanic 的失败一样关键
- 对每个场景截图，用视觉质量检查工具与参考图对比
- 得出最终结论：approve 或 reject，如果 reject 则附上具体问题列表

**你得到什么：** `.godotmaker/evaluation.json`（完整判定结果，按 mechanic id 列出 PASS/FAIL）、`e2e/screenshots/` 里的最新截图，以及 `.godotmaker/evaluation-runs/` 下的每轮评估证据归档。

**需要知道的：** 评估者不能写游戏代码，也不能碰 `src/`——对游戏文件严格只读。被拒不是失败，而是信息。问题列表会直接被 `/gm-fixgap` 使用。

---

## `/gm-fixgap`

**做什么：** 读取评估报告的问题列表，派 Worker 逐一修复（限定在当前 tag 范围内）。

**什么时候运行：** 在 `/gm-evaluate` 拒绝构建之后。

**背后发生了什么：**
- 读取 `.godotmaker/evaluation.json` 拿到产品层问题；恢复阶段如果 `.godotmaker/verify_report.json` 有上一轮 verify 留下的失败，也一并读入
- 生成或合并 `GAP.md`——一个按优先级排列的任务清单：每个 `C`/`J`/`G` 字母分组内，verify 来源的机械层失败排在前面，evaluation 来源的产品层问题排在后面
- 派 Worker 处理每个关键和重要问题，采用和 `/gm-build` 相同的 Worker → Verifier → Reviewer 循环
- 将当前的 `GAP.md` 归档到 `.godotmaker/gaps/<n>/`，保留每次迭代的记录

**你得到什么：** 更新后的游戏代码，`GAP.md` 被移入归档。

**需要知道的：** Tag 范围纪律在这里同样适用——修复触动先前 tag 代码必须有显式 GAP 项点名那些文件。`/gm-fixgap` 完成后，依次运行 `/gm-verify` 和 `/gm-evaluate`。这个循环持续下去，直到 `/gm-evaluate` 通过；如果跑了几轮都没进展，运行 `/gm-rescue` 来诊断卡住的是不是 godotmaker 框架本身。

---

## `/gm-accept`

**做什么：** 把通过评审的 tag 展示给你，记录你的决定。

**什么时候运行：** 在 `/gm-evaluate` 通过之后。

**背后发生了什么：**
- 向你展示按 tag 的总结：本 tag 交付的 mechanic、仍在通过的继承 mechanic、截图、已知限制、roadmap 中剩余的内容
- 询问：accept（继续 `/gm-finalize`）、reject（返回 `/gm-fixgap`），还是停下来
- 把你的答案记录在 `.godotmaker/stage.jsonl`

**你得到什么：** 一条已记录的本 tag 接受事件，或者明确的指示返回重做。

**需要知道的：** 在这里 accept 意味着 **当前 tag 准备封口**——不是说整个游戏完成。你随时可以在任意 tag 边界停下；最终决定权永远在你手里，不在工具。

---

## `/gm-finalize`

**做什么：** 封口 **当前 tag**——归档工作文档、写按 tag 的 changelog、执行 `git tag <Tag>`、重置每 tag 的运行时状态以便下一轮。

**什么时候运行：** 在 `/gm-accept` 记录了接受决定之后。

**背后发生了什么：**
- 验证项目仍能干净编译，`evaluation.json` 显示 `approve`
- 对照最终代码核对 `PLAN.md`、`STRUCTURE.md` 和场景文档，确保归档里的名称对应实际交付的系统和组件
- 把当前的 `GDD.md` / `PLAN.md` / `STRUCTURE.md` / `SCENES.md` / `MEMORY.md`（完整快照）和 `evaluation.json` 复制到 `docs/tags/<Tag>/`
- 生成 `docs/tags/<Tag>/CHANGELOG.md`，总结交付的 mechanic、新增系统、跨 tag refactor
- 在本地执行 `git tag <Tag>`（不 push）
- 截断 `.godotmaker/stage.jsonl` 并重置每 tag 的运行时状态，让下一个 `/gm-gdd` 在干净状态下开始

**你得到什么：** `docs/tags/<Tag>/` 下的不可变归档、一个本地 git tag、为下一轮准备好的干净每 tag 状态。

**需要知道的：** 这个 skill 不打 release zip；release 打包是单独的事（未来一个独立 skill）。`/gm-finalize` 不会 push git tag——这个决定是你的。

---

## `/gm-rescue`（主流程外）

**做什么：** 诊断流水线卡死的原因是 godotmaker 自身的缺陷（hooks、skills、config、templates），还是 godotmaker 范围之外的事（GDD 自相矛盾、AI 实现能力上限、环境问题）。

**什么时候运行：** 仅当流水线卡住时——通常是几轮 `/gm-fixgap` 都没法收敛，或者你怀疑是框架 bug 而非游戏代码 bug。

**背后发生了什么：**
- 读取运行时产出（`.godotmaker/current_role`、`stage.jsonl`、`evaluation.json`、最近的 `traces/`、`metrics.jsonl`）和当前 tag 的工作文档（`PLAN.md`、`GAP.md` 如存在、`MEMORY.md`）
- 走 godotmaker 各层（hooks → SKILL.md → config → templates → 共享 refs → tools），找匹配症状的缺陷
- 输出诊断到聊天——不改游戏代码、不写文件（唯二的写入是把 `.godotmaker/current_role` 设为 `rescue`，以及向 `stage.jsonl` 追加一条 rescue 事件）
- 如果发现 godotmaker 缺陷：起草一份 GitHub issue 草稿供你审阅后向上游提交
- 如果不是 godotmaker 的锅：明确告诉你，并指出可能的原因（GDD 逻辑、缺失资源、AI 能力上限等）

**你得到什么：** 一条聊天里的诊断消息。任何文件都不会被改动。

**需要知道的：** 隐私——issue 草稿默认不包含项目绝对路径、项目源码、GDD 内容。是否要进一步脱敏由你决定。`/gm-rescue` 不循环、不重试；诊断一次、报告一次。

---

## 什么是 tag？

一个 tag = 一轮完整的 `/gm-gdd` → `/gm-asset` → `/gm-build` → `/gm-verify` → `/gm-evaluate` →（fixgap 循环）→ `/gm-accept` → `/gm-finalize`。

`ROADMAP.md` 列出计划中的所有 tag。第一个 tag（永远是 `v0.1.0`）交付可玩闭环——最小可玩游戏。后续每个 tag 添加一组功能或重大调整。这样你可以渐进地扩展游戏，并且在每个 tag 边界都有机会停下、发布、或者转向。

要从全局视角了解各阶段是怎么衔接的，参见 [how-it-works.md](how-it-works.md)。
