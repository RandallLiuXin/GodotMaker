# 代码库指南

本页面对 GodotMaker 仓库逐目录进行深度介绍，帮助你在开始修改之前建立全局认知。如需简短概览，请参阅 [开发环境搭建](development-setup.md)。想了解各模块在运行时如何协作，请继续阅读本文。

## 仓库目录结构

```
GodotMaker/
├── hooks/                   8 个 hook 脚本 + hooks/metrics/ 子系统
├── agents/                  5 个子 Agent 定义（worker、verifier、reviewer、analyst、gdd-auditor）
├── skills/
│   ├── core/                角色技能 + 辅助技能 + _shared/
│   └── reviewer/            8 个审查技能（各含 gotchas.md + checklist.md）
├── tools/                   publish.py, check_env.py, check_project.py, asset_gen.py, migrate.py
├── config/                  config.yaml.default, stage_schemas.json, addon_versions.json
├── agent-runtimes/          runner 专属 reference、template 和 hook config
├── templates/               文档模板（GDD, PLAN, STRUCTURE, SCENES, ASSETS, GAP, MEMORY, TOC）
├── tests/                   ~320 个 hook 和工具的单元测试
├── docs/                    versioning.md, hooks.md, wiki/, update/, contributing/, reference/
├── shell/                   publish.sh / publish.ps1, report.sh / report.bat
├── migrations/              跨版本迁移脚本
├── VERSION                  语义版本号的唯一真实来源
└── CHANGELOG.md             每次发版的变更说明
```

---

## hooks/

八个 Python 脚本，负责强制执行流水线规则。每个脚本从 `sys.stdin` 读取 JSON payload，决定是否允许或拦截该操作，然后将 JSON 响应写入 stdout（静默放行时直接 exit 0，不输出任何内容）。

各脚本及其处理的事件：

| 脚本 | 事件 | 是否拦截 |
|--------|-------|---------|
| `session_start.py` | SessionStart | 否 |
| `check_file_permissions.py` | PreToolUse (Write\|Edit) | 是 |
| `stage_reminder.py` | PreToolUse (Write\|Edit) | 是 |
| `check_stage_prerequisites.py` | PreToolUse (Agent) | 是 |
| `check_asset_access.py` | PreToolUse (Read) | 是 |
| `log_subagent.py` | SubagentStart | 否 |
| `on_subagent_stop.py` | SubagentStop | 委托执行 |
| `check_worker_report.py` | 由 on_subagent_stop.py 调用 | 是 |
| `check_completion.py` | Stop | 是 |

Hook 注册关系（哪个脚本响应哪个事件）存储在
`agent-runtimes/<agent>/config/` 下，并发布到所选 runner 的项目级 hook
配置（`.claude/settings.json` 或 `.codex/hooks.json`）。

### hooks/metrics/

一个用于记录会话期间发生事件的小型子系统。Hook 通过调用 `record_event()` 将 JSON 行追加到 `.godotmaker/metrics_current.jsonl`（当前会话）和 `.godotmaker/metrics_total.jsonl`（全量生命周期日志）。`state.py` 模块负责在 `.godotmaker/state.json` 中管理可变的会话内计数器（拦截次数等）。`session_start.py` 在每次新会话开始时重置两者。

关于编写 hook 和使用 metrics API 的详细说明，请参阅 [编写 Hook](writing-a-hook.md)。

### 权限契约的三层划分

角色权限分布在三处，刻意有重叠，但每一层职责不同 — 改动其中一层时，要检查其他层是否要跟着动：

| 层 | 控制什么 | 真值来源 |
|----|---------|---------|
| `config/stage_schemas.json` | 角色完成了没？下一个角色启动前必须存在的产出文件清单。 | 由 `stage_reminder.py`（完成校验）和 `check_stage_prerequisites.py`（worker 派发前置检查）读取。 |
| `hooks/check_file_permissions.py` | 当前角色现在能写什么？每次 Write/Edit 工具调用都强制执行的 per-role 写权限白名单。 | 运行时权限的最终判定；schema 不定义写权限。 |
| `skills/core/gm-*/SKILL.md` 的 "Permission" 段落 | 给该角色的执行者读的人类版镜像。 | 应当与 hook 一致；若漂移，运行时以 hook 为准 — 但读 SKILL 的贡献者会被误导。 |

一个常见误解是把 `stage_schemas.json` 当成完整的写权限契约。它**不是** — 它只列出完成校验所需的产出文件。给某个角色的 schema 加文件**不会**自动获得写权限，还得同时扩展 hook 的白名单。

---

## agents/

子 Agent 定义文件，每个 Agent 对应一个 Markdown 文件。每个文件都带有 YAML front-matter（`name`、`description`、`model`）和系统 prompt 正文。`publish.py` 会将它们部署到 `<target>/.claude/agents/`，Claude Code 通过 `subagent_type` 识别调用。

| Agent | 职责 | 由谁派发 |
|-------|------|----------|
| `worker.md` | 端到端实现一个任务（代码 + 单元测试） | `/gm-build`、`/gm-fixgap` |
| `verifier.md` | 对 Worker 的产出进行机械校验（构建、测试、文件存在性） | `/gm-build`、`/gm-fixgap` |
| `reviewer.md` | 对照 `skills/reviewer/<domain>` 的 checklist 审查代码并报告问题 | `/gm-build`、`/gm-fixgap` |
| `analyst.md` | 分析用户提供的资源并输出 manifest | `/gm-asset` |
| `gdd-auditor.md` | 独立审计 GDD 草稿，对照 9 类 checklist 每轮返回 5–8 个补问 | `game-planner`（Rounds 6 + 7） |

派发协议（调用格式和 brief 模板）位于 `skills/core/_shared/{worker,verifier,reviewer,analyst}-dispatch.md`。`gdd-auditor` 直接由 `skills/core/game-planner/SKILL.md` 内联调用。

### 两轮 GDD 审计

`gdd-auditor` 是唯一一个派发协议**不**放在 `_shared/` 里的子 Agent。它只在 `game-planner` 的 Round 6 + Round 7 调用，派发逻辑离开那段访谈脚本就没意义。把它提到 `_shared/` 只会增加跳转，不会带来复用。

两轮，全部在新上下文中跑，使用同一个 `subagent_type`：

| 轮次 | Round | 输入 | 输出 | 这一轮存在的理由 |
|------|-------|------|------|------------------|
| 1 | Round 6 | GDD v1 + 空的 `Previously Asked` | 5–8 个补问 | 捕捉 planner 在访谈中遗漏的缺口 |
| 2 | Round 7 | GDD v2 + Round 6 的**完整原文**问题列表（填入 `Previously Asked`） | 5–8 个**新**问题 | 强迫 auditor 看二级缺口而不是重复自己 |

Round 7 brief 中的 `Previously Asked` 字段是必填项，不是可选项。不填就等于让 auditor 在新上下文里完全没有 pass 1 的记忆，结果会重复同样的问题、白白浪费一轮。`game-planner` SKILL.md 用 `**You MUST populate**` 标记这个字段，`gdd-auditor.md` 也把"在 `Previously Asked` 中重复问题"列为硬性禁止——两层一起强制同一份契约。

`auditor_model` 默认值是 `sonnet`（在 `config/config.yaml.default` 中配置）；审计任务是 checklist 驱动的，不需要 opus 级推理。

---

## skills/core/

角色技能和辅助技能，每个技能对应一个目录。每个目录至少包含一个带有 YAML front-matter 和 prompt 正文的 `SKILL.md`。

**角色技能（9 个）：** `gm-scaffold`、`gm-gdd`、`gm-asset`、`gm-build`、`gm-verify`、`gm-evaluate`、`gm-fixgap`、`gm-accept`、`gm-finalize`。这些技能与 `/gm-*` 斜杠命令一一对应。每个角色技能的第一个动作是将角色名写入 `.godotmaker/current_role`，这正是 `check_file_permissions.py` 用来执行写入规则的依据。

**辅助技能（11 个）：** `game-planner`、`project-scaffold`、`godot-api`、`gecs`、`input-mapper`、`headless-build`、`gdunit-driver`、`godot-e2e`、`visual-qa`、`screenshot`、`mcp-driver`。这些是由角色技能加载的参考文档，用户不会直接调用它们。

### skills/core/_shared/

任何被超过一个技能使用的参考文档，都以此处为唯一真实来源保存。例如：`worker-dispatch.md`、`verifier-dispatch.md`、`reviewer-dispatch.md`、`analyst-dispatch.md`。

发布时，`publish_shared_refs()` 读取 `_shared/manifest.json`，将每个源文件写入所有列出的消费技能的 `references/` 文件夹。被部署的副本带有 `<!-- AUTO-GENERATED -->` 头部，每次发布都会被覆盖。

**编辑规则：**
- 只编辑 `_shared/<file>.md` 下的源文件，永远不要编辑已部署的副本。
- 在消费技能的 `SKILL.md` 中，通过 `references/<file>.md` 引用该文档（这是部署后的路径，`_shared/` 在已发布项目中并不存在）。
- 新增或修改共享文档后，运行 `python -m pytest tests/tools/test_publish_shared.py -q` 确认 manifest 与所有消费者引用保持一致。

manifest 的 schema、添加/移除流程和调试技巧见 `docs/contributing/shared-refs.md`。

---

## skills/reviewer/

八个审查技能，每个领域一个：`physics`、`animation`、`ui`、`tilemap`、`navigation`、`shader`、`audio`、`particles`。

每个审查技能目录包含恰好三个文件：
- `SKILL.md` — 审查员 prompt
- `gotchas.md` — 领域特定陷阱目录（LLM 容易犯错的地方）
- `checklist.md` — 与 gotcha ID 对应的系统性检查项

审查子 Agent（由 `gm-build` 和 `gm-fixgap` 分发）根据 worker 输出中出现的 Godot 类和 API 动态读取这些文件，并不存在静态分发列表——审查员自行挑选相关的领域文件。关于审查技能结构的详细说明，见 [编写技能](writing-a-skill.md)。

---

## tools/

贡献者和用户直接运行的 Python CLI 脚本。

| 工具 | 用途 |
|------|---------|
| `publish.py` | 将 GodotMaker 部署到目标 Godot 项目 |
| `check_env.py` | 验证 Godot、Python 和 API key 是否正确配置 |
| `check_project.py` | 检验已生成项目中的缺失文件和损坏路径 |
| `asset_gen.py` | 通过 Gemini / OpenAI / xAI 生成 API 后端美术资源（由 `/gm-asset` 调用，也可独立运行） |
| `migrate.py` | 在任何非 MAJOR 升级时把未应用的迁移脚本应用到目标项目；也通过 `--new <slug>` 生成新脚本模板 |

### publish.py 如何串联一切

运行 `python tools/publish.py <target>` 时：

1. 从仓库根目录读取 `VERSION`，与 `<target>/.godotmaker/version` 比较。MINOR / MAJOR 升级时弹出提示或直接拦截。
2. 扁平复制技能：`skills/core/` 和 `skills/reviewer/` 下的所有目录会写入所选 agent 的技能目录（Claude Code 为 `<target>/.claude/skills/`，Codex 为 `<target>/.agents/skills/`）。名称以 `_` 开头的目录（即 `_shared/`）会被 `publish_skills()` 跳过；共享文档改由 `publish_shared_refs()` 部署到消费技能的 `references/` 文件夹中。
3. 复制 hooks → `<target>/.godotmaker/hooks/`。
4. 复制 tools → `<target>/tools/`。
5. 复制 templates 到所选 agent 的模板目录。
6. 复制 `config/stage_schemas.json` → `<target>/.godotmaker/stage_schemas.json`。
7. 首次安装（或使用 `--force`）时：写入对应 agent 的项目指令文件（`CLAUDE.md` 或 `AGENTS.md`），提示配置 `godotmaker.yaml`；Claude Code 目标还会写入 `.claude/settings.json`。
8. 将当前版本号写入 `<target>/.godotmaker/version`。

---

## config/

| 文件 | 控制内容 |
|------|-----------------|
| `settings.json` | Hook 注册：哪些脚本响应哪些 Claude Code 事件 |
| `stage_schemas.json` | 每个角色的必要输出和程序化检查（key 为角色名） |
| `addon_versions.json` | 按引擎版本锁定的 Godot 插件版本 |

`stage_schemas.json` 是 `stage_reminder.py` 和 `check_stage_prerequisites.py` 都会读取的 schema。其 key 为角色名（`scaffold`、`gdd`、`build` 等），每个值包含可选的 `files` 数组（必须存在于磁盘上的路径）和可选的 `checks` 数组（程序化验证器名称）。完整 schema 说明见 [编写技能](writing-a-skill.md)。

---

## templates/

Markdown 文档模板，由 `publish.py` 部署到新游戏项目的所选 agent 模板目录下。角色技能在工作过程中填充这些模板。模板包括：`GDD.md`、`PLAN.md`、`STRUCTURE.md`、`SCENES.md`、`ASSETS.md`、`GAP.md`、`MEMORY.md`、`TOC.md`、`game-claude.md`。

---

## tests/

测试套件，按覆盖对象组织。

```
tests/
├── hooks/
│   ├── helpers.py                       共享工具函数：run_hook, is_blocked, write_completed_roles, ...
│   ├── test_check_completion.py
│   ├── test_check_file_permissions.py
│   ├── test_check_stage_prerequisites.py
│   ├── test_check_worker_report.py
│   ├── test_metrics.py
│   ├── test_session_start.py
│   └── test_stage_reminder.py
├── tools/
│   ├── conftest.py
│   ├── test_addon_versions.py
│   ├── test_check_classname.py
│   ├── test_check_env.py
│   ├── test_check_project.py
│   ├── test_migrate.py
│   ├── test_publish.py
│   └── test_publish_shared.py
└── test_pipeline_e2e.py                 端到端流水线冒烟测试
```

`pyproject.toml` 将 `hooks/` 加入 `pythonpath`，使 hook 测试中的 `from metrics import ...` 无需安装任何包即可解析。关于编写新测试，请参阅 [测试](testing.md)。

---

## docs/

与代码共存于仓库的人类可读文档。

| 路径 | 内容 |
|------|-----------------|
| `docs/hooks.md` | 每个 hook 的精确参考（重写后版本） |
| `docs/versioning.md` | 版本方案与升级行为 |
| `docs/wiki/` | 面向用户和贡献者的 Wiki |
| `docs/contributing/` | 共享引用 schema、发版清单 |
| `docs/update/` | `next.md`（待发布变更）及归档的 `vX.Y.Z.md` 文件 |
| `docs/reference/` | API 和配置参考存根 |

---

## shell/

贡献者从终端运行的两个操作的薄包装脚本：

- `publish.sh` / `publish.ps1` — 委托调用 `python tools/publish.py`
- `report.sh` / `report.bat` — 运行 `python -m hooks.metrics.reporter`，从 JSONL metrics 文件生成 HTML 报告

---

## migrations/

`tools/migrate.py` 在任何非 MAJOR 升级时运行的迁移脚本。脚本直接放在 `migrations/` 下，按 UTC 时间戳命名（`<YYYYMMDDhhmmss>_<slug>.py`），按时间序执行。每个目标项目在 `.godotmaker/applied_migrations.json` 里独立追踪已应用的 ID；整套机制与产品 MAJOR.MINOR.PATCH 完全解耦。MAJOR 升级完全跳过迁移、改用 `--force` 干净重装，重装后 `baseline_applied()` 会把所有当前迁移重新标记为已应用。完整升级流程见 [发版流程](release-process.md)。
