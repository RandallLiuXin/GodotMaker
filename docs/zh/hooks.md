# Hooks 参考手册

GodotMaker 所有 Hook 的完整参考。Hook 是 Python 脚本，在 Claude Code 事件上自动运行，用于执行流水线规则。

Hook 注册关系按 runner 分开维护：Claude Code 使用
`agent-runtimes/claude-code/config/settings.json`，Codex 使用
`agent-runtimes/codex/config/hooks.json`。脚本通过发布流程部署到
`.godotmaker/hooks/`。

---

## Hook 清单

| Hook | 事件 | 匹配器 | 是否阻止？ | 用途 |
|------|------|--------|-----------|------|
| `session_start.py` | SessionStart | — | 否 | 清除会话指标，重置状态 |
| `check_file_permissions.py` | PreToolUse | Write\|Edit | 是 | 由 `.godotmaker/current_role` 驱动的每角色写规则 |
| `stage_reminder.py` | PreToolUse | Write\|Edit | 是 | 检测 `stage.jsonl` 追加操作，验证角色输出，注入下一角色提示 |
| `check_stage_prerequisites.py` | PreToolUse | Agent | 是 | Worker 派发前，验证前置角色已完成且其产出存在 |
| `check_asset_access.py` | PreToolUse | Read | 是 | 在活跃角色期间，阻止主代理读取 `assets/` 中的图片文件 |
| `log_subagent.py` | SubagentStart | — | 否 | 记录子代理启动指标（角色检测、agent_id） |
| `on_subagent_stop.py` | SubagentStop | — | 是 | 分发器：串行执行 `log_subagent.handle_stop` + `check_worker_report`，避免指标文件竞态 |
| `check_completion.py` | Stop | — | 是 | 最终门控：仅针对 `build` / `fixgap`，若派发了 Worker 但未运行 Verifier + Reviewer 则阻止结束 |

---

## 详细说明

### session_start.py

**事件：** SessionStart
**是否阻止：** 从不

每次会话开始时执行三件事：

1. 清除 `metrics_current.jsonl`（会话日志）并重置 `state.json` 计数器。
2. 删除上一会话留下的过期 `.godotmaker/current_role`，让下一个 `/gm-*` 技能写入新值。
3. 读取 `.godotmaker/version` 并将 `[GodotMaker vX.Y.Z]` 作为 `additionalContext` 注入，让角色和用户知道部署的是哪个框架版本。

### check_file_permissions.py

**事件：** PreToolUse（Write|Edit）
**是否阻止：** 是

读取 `.godotmaker/current_role`（每个 `/gm-*` 技能的第一个动作写入）并应用该角色的写规则。各角色摘要：

| 角色 | 可写内容 |
|------|----------|
| `scaffold` | 任何内容（项目初始化） |
| `gdd` | `.md` 规划文档、`project.godot`、`.godotmaker/`（不含 `assets/`） |
| `asset` | `ASSETS.md`、`.godotmaker/`（图片文件通过 `asset_gen.py` Bash 或 Analyst 子代理处理） |
| `build` / `fixgap` | `e2e/` 中不可写；游戏代码（`.gd` / `.tscn` / `.tres`）不可直接写——必须派发 Worker |
| `verify` | 仅 `.godotmaker/stage.jsonl`、`.godotmaker/current_role` 和 `.godotmaker/verify_report.json`（其他地方只读） |
| `evaluate` | `e2e/`、`.godotmaker/evaluation.json`、`.godotmaker/stage.jsonl`、`.godotmaker/current_role` |
| `accept` / `finalize` | 除 `e2e/` 和游戏代码（`.gd` / `.tscn` / `.tres`）外的任何内容 |

在流水线角色活跃期间，子代理会被阻止写入 `e2e/`（评估器专属）和规划文档（`PLAN.md` / `STRUCTURE.md` / `ASSETS.md` / `GAP.md`）；它们通过报告来记录变更。

未设置角色时，表示当前没有活跃的 `/gm-*` 流水线角色。该 Hook 只记录文件操作，不阻止写入，因此用户可以在 GodotMaker 项目目录中正常开启普通 coding-agent 对话。

同时为每次文件操作记录 `FILE_WRITE` / `FILE_EDIT` 指标事件。

### stage_reminder.py

**事件：** PreToolUse（Write|Edit）
**是否阻止：** 是

当 `/gm-*` 技能向 `.godotmaker/stage.jsonl` 追加角色完成事件时触发。每行格式为 `{"role": <role>, "ts": <iso>}`。

1. **验证角色产出** — 读取 `config/stage_schemas.json`（键为角色名，非阶段编号），检查 `files` 是否存在并运行 `checks` 中的程序化验证器。验证失败则阻止追加。
2. **注入提示** — 通过 `ROLE_NEXT` 表指向下一个角色的 `/gm-*` 指令。

程序化检查：

| 检查 | 角色 | 断言内容 |
|------|------|----------|
| `plan_all_verified` | `build` | `PLAN.md` 中每个任务行的状态为 `verified`（无 `pending` / `in_progress` / `completed`） |
| `gap_archived` | `fixgap` | `GAP.md` 已被移动到 `.godotmaker/gaps/<iteration>/GAP.md` |

角色产出 Schema 位于 `config/stage_schemas.json`。当前结构：
- `scaffold` → `project.godot`
- `gdd` → `GDD.md`、`PLAN.md`、`STRUCTURE.md`
- `evaluate` → `.godotmaker/evaluation.json`
- `finalize` → `.godotmaker/final_report.json`
- `asset` / `verify` / `accept` 依赖各自 SKILL.md 中的 Resume Check。

### check_stage_prerequisites.py

**事件：** PreToolUse（Agent）
**是否阻止：** 是

仅对驱动 Worker 编排的两个角色执行检查：

| 角色 | 前置角色 | 额外检查 |
|------|----------|----------|
| `build` | `gdd` 已记录在 `stage.jsonl` 中 | `project.godot` 存在（scaffold 产物，生命周期内唯一） |
| `fixgap` | `evaluate` 已记录在 `stage.jsonl` 中 | （通过 `evaluate` schema → `.godotmaker/evaluation.json` 验证） |

Hook 还会重新验证前置角色在 `config/stage_schemas.json` 中的 `files`——对于 `build`，确认 `GDD.md`、`PLAN.md`、`STRUCTURE.md` 仍在磁盘上；对于 `fixgap`，确认 `.godotmaker/evaluation.json` 仍存在。

其他有派发行为的角色（如 `asset` → Analyst）通过 SKILL.md 的 Resume Check 进行自我验证；其前置条件不适合这个 Hook 的角色完成模型。仅检查主代理（gm-* 技能本身），不检查子-子代理的派发。

### check_asset_access.py

**事件：** PreToolUse（Read）
**是否阻止：** 是

仅在流水线角色活跃时（存在 `.godotmaker/current_role`），阻止主代理读取 `assets/` 中的图片文件。
图片扩展名：.png、.jpg、.jpeg、.svg、.webp、.gif、.bmp、.tga。

没有活跃角色的普通对话被允许。子代理（Analyst）被允许。非图片文件（.json、.ogg）被允许。

目的：强制主代理将资源分析委托给 Analyst 子代理，而不是消耗上下文来读取原始图片数据。

### log_subagent.py

**事件：** SubagentStart（以及 `on_subagent_stop.py` 调用它处理 SubagentStop）
**是否阻止：** 从不

**SubagentStart：** 检测角色并记录 `SUBAGENT_START` 指标，包括 `agent_id`、`agent_type`、`role`、`description`。

角色检测顺序：
1. **运行时提供的 `agent_type`** — 如果 Claude Code 传入的 `agent_type` 匹配 `KNOWN_ROLES`（`worker`、`verifier`、`reviewer`、`analyst`），则使用该值。这是 Claude Code 在调用 `Agent({subagent_type: "verifier", ...})` 时加上的结构化标识，代理无法伪造。
2. **描述前缀回退** — 如果 `agent_type` 是通用值，则回退到 `detect_role_from_description`：
   1. `analyst:` → analyst
   2. `worker:` → worker
   3. `verifier:` / `verify:` → verifier
   4. `reviewer:` / `review:` → reviewer

**handle_stop：** 由 `on_subagent_stop.py` 调用。从助手消息中提取报告类型、状态、变更文件。从匹配的启动事件中查找角色。记录 `SUBAGENT_STOP` 指标以及结果特定事件：`WORKER_DONE`、`VERIFIER_PASS` 等。

### on_subagent_stop.py

**事件：** SubagentStop
**是否阻止：** 是（委托给 `check_worker_report`）

`SubagentStop` 事件的单一分发器。读取一次 stdin 后串行运行：

1. `log_subagent.handle_stop(data)` — 记录指标，保存追踪（从不阻止）
2. `check_worker_report.main_with_data(data)` — 验证报告（可能阻止）

**为什么使用分发器：** Claude Code 默认并行运行多个 `SubagentStop` Hook。两个处理程序都会操作 `metrics_current.jsonl`——`log_subagent` 读取，`check_worker_report` 写入——这会导致间歇性的 `JSONDecodeError` 崩溃。在单个进程内串行执行消除了竞态条件。

### check_worker_report.py

**事件：** SubagentStop（通过 `on_subagent_stop.py` 调用）
**是否阻止：** 是

仅在 `/gm-*` 流水线角色活跃时验证子代理角色的报告格式和内容。没有 `.godotmaker/current_role` 时，普通子代理对话被允许，该 Hook 不阻止。

**格式检测流程：**
1. 从消息内容检测 `report_type`（分层：精确标记 → 正则 → 回退）
2. 若检测到 `report_type` → 检查该类型所需的章节
3. 若 `report_type` 为 None 但从启动事件得知角色 → 阻止并要求提交格式化报告

**每角色必需章节：**

| 角色 | 必需章节 |
|------|----------|
| worker | Status, Files Changed, Tests, Build, Memory Entry |
| verifier | Overall, Results, Adversarial Probes |
| reviewer | Reviewers Matched, ECS Review, Issues Found, Summary |
| analyst | Status, Asset Summary, Art Style Summary, Files Generated |

**Worker 专项深度检查：**
- `check_test_substance()` — Tests 章节必须包含单元测试的实际通过/失败输出
- `check_resource_paths()` — .gd 文件中的 `res://` 路径必须存在
- `check_classname_conflicts()` — `class_name` 声明不得与 Godot 内置名称冲突

**进度提示：** 验证成功后，注入一条进度摘要（已完成的 Worker、Verifier、Reviewer 数量）作为附加上下文。

**Reviewer 内容检查：** ECS Review 和 Issues Found 章节各自必须有至少 50 个字符的内容，防止空洞或走过场的审查。

**防死锁：** `BLOCK_LIMIT = 2`，每个 `agent_id` 最多 2 次拦截——超过 2 次后强制放行并给出警告，而不是永远阻止。

**已知缺口：**
- Verifier 报告：没有 Hook 验证 Verifier 确实运行了测试（仅检查格式）
- 没有针对每个 Worker 的截图验证（截图是 `/gm-evaluate` 中评估器的职责）

### check_completion.py

**事件：** Stop
**是否阻止：** 是

当活跃的 gm-* 技能尝试结束对话时的最终门控。仅对 Worker 派发角色（`build`、`fixgap`）生效；对其他所有角色该 Hook 是空操作，它们通过各自 SKILL.md 的 Resume Check 自我执行规则。

**Worker 派发严谨性检查：** 如果本次会话中派发了任何 Worker，则 Verifier 和 Reviewer 都必须也已运行（根据 gm-build / gm-fixgap 规则）。如果只运行了 Worker，Hook 会阻止并列出缺失的角色。

**防死锁：** `BLOCK_LIMIT = 5` — 同一会话中 5 次阻止后，强制放行并给出警告，而不是永远阻止。

---

## 事件流程图

```
SessionStart
  └── session_start.py (清除指标)

PreToolUse(Write|Edit)
  ├── check_file_permissions.py (从 current_role 读取每角色写规则)
  └── stage_reminder.py (验证 stage.jsonl 追加，注入下一角色指针)

PreToolUse(Agent)
  └── check_stage_prerequisites.py (若前置角色未完成则阻止 build/fixgap)

PreToolUse(Read)
  └── check_asset_access.py (活跃角色期间阻止主代理读取 assets/ 中的图片)

SubagentStart
  └── log_subagent.py (记录启动 + 角色)

SubagentStop
  └── on_subagent_stop.py (串行：log_subagent.handle_stop → check_worker_report)

Stop
  └── check_completion.py (仅 build/fixgap 的严谨性检查；其他角色为空操作)
```

---

## 已知缺口（TODO）

1. **Verifier 测试执行：** 没有 Hook 验证 Verifier 确实运行了测试（而不只是报告了格式正确的结果）。抽查仅在提示层面进行。
