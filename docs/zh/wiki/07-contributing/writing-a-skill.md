# 编写技能

技能是告诉所选 coding agent 在流水线每个阶段应该做什么的指令包。一个技能是一个文件夹，其中包含一个 `SKILL.md` prompt、可选的 `references/` 文档以及可选的辅助文件。当 `publish.py` 运行时，每个技能都会被扁平复制到所选 agent 的项目本地技能目录（Claude Code 为 `.claude/skills/`，Codex 为 `.agents/skills/`）。

## 我在写哪种技能？

GodotMaker 有三个技能层级，分别存放在不同的文件夹中：

| 层级 | 文件夹 | 调用方式 |
|-------|--------|-----------|
| **角色技能** | `skills/core/gm-*/` | `godotmaker-cli` 或手动 `/gm-build`、`/gm-verify` 等 |
| **辅助技能** | `skills/core/<name>/` | 其他技能将其作为参考文档加载 |
| **审查技能** | `skills/reviewer/<name>/` | 由 `gm-build` / `gm-fixgap` 分发的审查子 Agent |

决策树：
- 新增一个拥有流水线阶段的 `/gm-*` 命令 → **角色技能**
- 新增多个现有技能都需要引用的领域知识 → **辅助技能**（如果两个或更多技能需要使用，很可能也是 `_shared/` 的候选）
- 为新的 Godot 子系统（例如 shader、navigation）新增检查 → **审查技能**

---

## 技能结构

每个技能目录至少需要一个文件：

```
skills/core/my-skill/
└── SKILL.md            必需，Claude 读取的 prompt。

可选：
├── references/         SKILL.md prompt 加载的辅助文档。
└── assets/             技能所需的任何静态文件。
```

### SKILL.md front-matter

每个 `SKILL.md` 都以 YAML front-matter 块开头：

```yaml
---
name: my-skill
description: |
  一段说明这个技能做什么以及 Claude 何时应该使用它的介绍。
  尽量具体："Use when..." 和 "Does NOT handle..." 有助于匹配。
disable-model-invocation: true
---
```

`name` 字段是斜杠命令的标识符。`description` 字段是 Claude Code 用来将用户请求匹配到正确技能的依据。`disable-model-invocation: true` 对**角色技能是必需的**——它防止该技能被模型隐式调用，只能通过斜杠命令显式触发。

来自 `skills/core/gm-build/SKILL.md` 的真实示例：

```yaml
---
name: gm-build
description: |
  Implement game systems via worker dispatch. Covers risk-first then main implementation.
  Dispatches workers until PLAN is clean, then runs one verify+review pass; loops until convergence.
  Explicit invocation only — use /gm-build.
disable-model-invocation: true
---
```

### SKILL.md 正文

front-matter 之后是 prompt 正文。角色技能的常见结构：

1. **会话初始化** — 技能必须执行的第一个动作（例如写入 `.godotmaker/current_role`）。
2. **恢复检查** — 读取 `stage.jsonl`，决定是继续、恢复还是提示用户运行某个命令停止。
3. **硬性规则** — 技能绝不能做的事（hook 通常作为后备手段来强制执行）。
4. **步骤** — 该角色工作的编号指令。
5. **完成** — 如何记录角色完成事件。

使用 `$ARGUMENTS` 作为用户在斜杠命令后传入内容的占位符。

---

## 角色技能细节

### 文件锁定 — current_role

每个角色技能的第一个动作必须是：

```
Write the role name to .godotmaker/current_role.
```

例如，`/gm-build` 写入 `build`。这正是 `check_file_permissions.py` 用来判断当前会话应用哪条写入规则的依据。

### 恢复检查

每个角色技能读取 `.godotmaker/stage.jsonl`（每行一个 JSON 对象，格式为 `{"role": X, "ts": Y}`），然后决定：

- 如果前置角色的完成事件缺失 → 停止并告知用户应先运行哪个命令。
- 如果本角色的完成事件已存在 → 告知用户该角色已完成，并建议下一个命令。
- 否则 → 继续执行（包括从中断处恢复）。

### 完成事件格式

角色完成时，向 `.godotmaker/stage.jsonl` 追加一行：

```json
{"role": "build", "ts": "2026-04-27T12:00:00Z"}
```

`append_stage_event.py` 会在追加事件前验证必要输出。对于提供 Write/Edit hook 的 runtime，`stage_reminder.py` 只注入下一个角色的指引。

### 必要输出与 stage_schemas.json

`config/stage_schemas.json` 声明了每个角色在记录完成事件之前必须产生的内容。schema 以角色名为 key：

```json
{
  "scaffold": {
    "files": ["project.godot"]
  },
  "gdd": {
    "files": ["GDD.md", "PLAN.md", "STRUCTURE.md"]
  },
  "build": {
    "checks": ["plan_all_verified"]
  },
  "evaluate": {
    "files": [".godotmaker/evaluation.json"]
  }
}
```

- `files` — 必须存在于磁盘上的路径（相对于项目根目录）。
- `checks` — append 工具通过 `completion_gate.py` 运行的程序化验证器名称。当前验证器包括 `plan_all_verified` 和 `gap_archived_unless_handoff`。

如果你新增了一个角色，在这里添加对应条目。如果角色没有可通过文件存在性验证的必要输出，可以省略条目或保留空对象。

### 共享参考文档

如果你写入 `references/` 的参考文档也会被其他技能用到，请将它放在 `skills/core/_shared/` 下，并在 `_shared/manifest.json` 中添加条目。manifest schema 和添加/移除流程见 `docs/contributing/shared-refs.md`。在你的 SKILL.md 中，通过 `references/<file>.md` 引用它（这是部署后的路径，`_shared/` 在已发布项目中不存在）。

---

## 审查技能细节

审查技能必须包含全部三个文件：

```
skills/reviewer/my-domain/
├── SKILL.md        审查员 prompt
├── gotchas.md      领域特定陷阱（LLM 容易犯错的地方）
└── checklist.md    与 gotcha ID 对应的系统性检查项
```

审查子 Agent 根据 worker 输出中出现的 Godot 类和 API 动态读取 `gotchas.md` 和 `checklist.md`。不存在静态分发列表——审查员自行挑选相关的领域文件。

### gotchas.md 格式

每个条目描述一个具体陷阱：

```markdown
## G1. 简短的描述性标题 [GDScript] [C#]

**Symptom**: 开发者看到的报错或异常现象。

**Root cause**: Godot 为什么会这样表现。

**Correct approach**: 正确的写法。

**Wrong approach**: LLM 通常会生成什么（以及为什么会失败）。
```

使用 `[GDScript]`、`[C#]` 或两者同时标注条目。

### checklist.md 格式

检查项有编号，并与 gotcha ID 交叉引用：

```markdown
## Static Checks

### S1. 检查名称 → G1
Grep for [pattern]:
- [表示存在问题的条件]
- [期望的正确模式]
```

静态（基于 grep）检查使用 `S` 前缀，运行时检查使用 `R` 前缀。

### 审查报告格式

`check_worker_report.py` hook 验证审查报告是否包含以下章节：`### Reviewers Matched`、`### ECS Review`、`### Issues Found`、`### Summary`。`ECS Review` 和 `Issues Found` 章节的内容至少需要 50 个字符——空报告或流于形式的报告会被拦截。

---

## 辅助技能细节

辅助技能是纯参考内容——没有斜杠命令，也不需要 `disable-model-invocation: true`。它们通过 `references/<file>.md` 由其他技能加载。例如，`gecs` 技能提供 ECS 使用模式和已知陷阱，供 `gm-build` 引用。

不需要注册步骤。`publish.py` 将 `skills/core/` 下的每个目录（除 `_shared/` 外）都复制到目标项目，消费技能通过 `references/` 路径引用辅助技能的内容。

---

## 测试你的技能

1. 发布到临时项目：

   ```bash
   python tools/publish.py /path/to/scratch-game
   ```

2. 在 Claude Code 中打开临时项目，运行斜杠命令。

3. 检查输出：
   - 对于角色技能：检查 `stage.jsonl`、`config/stage_schemas.json` 中列出的预期文件，以及 `.godotmaker/current_role` 是否被正确写入。
   - 对于审查技能：检查报告是否包含所有必需章节，以及 gotcha 交叉引用是否准确。

4. 如果技能引用了共享文档，运行：

   ```bash
   python -m pytest tests/tools/test_publish_shared.py -q
   ```

   确认 manifest 与部署路径保持一致。
