# 编写 Hook

Hook 是 coding-agent runtime 在会话特定事件发生时调用的小型 Python 脚本。它们强制执行 AI 自身无法绕过的规则——文件权限边界、角色完成前的必要输出、报告质量门禁。Hook 注册按 runner 区分：Claude Code 和 Codex 使用配置文件，OpenCode 使用 plugin adapter。脚本存放在 `hooks/` 下，由 `publish.py` 部署到 `.godotmaker/hooks/`。

关于每个 hook 的完整参考（精确的 payload、拦截条件、边界情况），请参阅 [../../hooks.md](../../hooks.md)。本页专注于如何编写新的 hook，而不是讲解每个现有 hook 的工作原理。

---

## Hook 的结构

一个 hook 就是一个如下形式的 Python 脚本：

```python
import json
import sys

def main():
    data = json.load(sys.stdin)

    # 检查事件内容
    tool_name = data.get("tool_name", "")
    file_path = data.get("tool_input", {}).get("file_path", "")

    # 静默放行——exit 0，不输出任何内容到 stdout
    if not should_block(file_path):
        return

    # 拦截——向 stdout 写入结构化 JSON，exit 0
    # （runner hook 入口读取 stdout 来做决策，而不是依赖退出码）
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": data.get("hook_event_name", "PreToolUse"),
            "permissionDecision": "deny",
            "permissionDecisionReason": "显示给 Agent 的原因说明。"
        }
    }))

if __name__ == "__main__":
    main()
```

三种结果：

| 结果 | 如何发出信号 |
|---------|-----------------|
| 静默放行 | Exit 0，stdout 无输出 |
| 放行并附带提示 | Exit 0，向 stdout 输出带 `additionalContext` 的 JSON |
| 拦截操作 | Exit 0，向 stdout 输出带 `permissionDecision: "deny"`（PreToolUse）或 `decision: "block"`（Stop / SubagentStop）的 JSON |

runner hook 入口读取 stdout 来做决策，不使用退出码来执行拦截。如果 hook 崩溃（非零退出，或 stdout 输出格式错误的 JSON），runtime 可能只记录错误并继续执行——hook 绝不能因崩溃而静默地破坏流水线。

### PreToolUse 的拦截格式

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "人类可读的解释。"
  }
}
```

### Stop 和 SubagentStop 的拦截格式

```json
{
  "decision": "block",
  "reason": "人类可读的解释。"
}
```

### 放行并附带上下文

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "additionalContext": "注入到对话中的文本内容。"
  }
}
```

---

## 可以挂载的事件

| 事件 | 触发时机 | 关键 payload 字段 |
|-------|--------------|-------------------|
| `SessionStart` | 受支持的 root runtime 会话开始时 | `hook_event_name` |
| `PreToolUse` (Write\|Edit) | 每次文件写入或编辑之前 | `tool_name`, `tool_input.file_path`, `tool_input.content`, `agent_id` |
| `PreToolUse` (Agent) | 每次分发子 Agent 之前 | `tool_name`, `tool_input.description`, `agent_id` |
| `PreToolUse` (Read) | 每次文件读取之前 | `tool_name`, `tool_input.file_path`, `agent_id` |
| `SubagentStart` | 子 Agent 开始运行时 | `agent_id`, `agent_type`, `description` |
| `SubagentStop` | 子 Agent 运行完成时 | `agent_id`, `agent_type`, `last_assistant_message` |
| `Stop` | 主 Agent 尝试结束会话时 | `agent_id`（主 Agent 为空） |

`agent_id` 对主 Agent 为空，对子 Agent 为非空。Hook 通过这一字段区分角色技能和其 worker。

不同 runner 的 payload 不完全一致。Claude Code 和 Codex 提供 Claude-style
`agent_id`、`SubagentStart` 和 `SubagentStop` payload。OpenCode 使用 adapter
plugin，不暴露同等的子 Agent 生命周期 payload；依赖这些字段的 hook 必须明确只支持
Claude Code / Codex，或提供显式的 OpenCode fallback。

---

## 现有 Hook 概览

以下为简要摘要。每个 hook 的完整说明见 [../../hooks.md](../../hooks.md)。

| 脚本 | 事件 | 是否拦截 | 用途 |
|--------|-------|---------|---------|
| `session_start.py` | SessionStart | 否 | 清空会话 metrics 和状态，将 GodotMaker 版本注入上下文 |
| `check_file_permissions.py` | PreToolUse (Write\|Edit) | 是 | 根据 `.godotmaker/current_role` 强制执行每个角色的写入规则 |
| `stage_reminder.py` | PreToolUse (Write\|Edit) | 是 | 拦截 `stage.jsonl` 追加操作，验证角色输出，注入下一角色指引 |
| `check_stage_prerequisites.py` | PreToolUse (Agent) | 是 | 前置角色未完成时，阻止 `build` / `fixgap` 分发 worker |
| `check_asset_access.py` | PreToolUse (Read) | 是 | 阻止主 Agent 直接读取 `assets/` 中的图片文件（强制使用分析师子 Agent） |
| `log_subagent.py` | SubagentStart | 否 | 记录子 Agent 启动及角色信息；由 `on_subagent_stop.py` 再次调用以记录停止 metrics |
| `on_subagent_stop.py` | SubagentStop | 委托执行 | 串行调度器：在同一进程中依次运行 `log_subagent.handle_stop` 和 `check_worker_report.main_with_data`，避免 metrics 文件竞争条件 |
| `check_completion.py` | Stop | 是 | `build` / `fixgap` 的最终门禁：若 worker 运行后未经过验证器 + 审查员则拦截 |

---

## 防死锁模式

两个 hook 可能对同一个 Agent 反复拦截：`check_worker_report.py`（在报告有效之前阻止子 Agent 停止）和 `check_completion.py`（在质量步骤完成之前阻止主 Agent 停止）。如果没有安全阀，顽固的 Agent 可能被无限期拦截。

两个 hook 都实现了存储在 `.godotmaker/state.json` 中的 `BLOCK_LIMIT` 计数器：

- `check_worker_report.py` 使用 key `worker_report_block:{agent_id}`，`BLOCK_LIMIT = 2`。同一子 Agent 被拦截 2 次后，hook 强制放行并附带警告。
- `check_completion.py` 使用 key `stop_block_count`，`BLOCK_LIMIT = 5`。同一会话中被拦截 5 次后，hook 强制放行并附带警告。

当你编写可能反复拦截的 hook 时，实现相同的模式：

```python
from metrics import state

BLOCK_LIMIT = 3
COUNTER_KEY = "my_hook_block_count"

count = state.increment(COUNTER_KEY)
if count > BLOCK_LIMIT:
    # 强制放行并附带警告
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "...",
            "additionalContext": f"POTENTIAL BUG: Force-allowing after {BLOCK_LIMIT} blocks."
        }
    }))
    return
```

这些计数器在每次新会话开始时由 `session_start.py` 重置。

---

## Metrics 与状态

Hook 可以读写两种持久化数据。

### Metrics（只追加）

调用 `hooks/metrics/__init__.py` 中的 `record_event()` 追加一行 JSONL：

```python
from metrics import record_event, EventType

record_event(EventType.HOOK_BLOCK, hook="my_hook", reason="...", file="player.gd")
```

事件同时写入两个文件：
- `.godotmaker/metrics_current.jsonl` — 当前会话，在 `SessionStart` 时清空
- `.godotmaker/metrics_total.jsonl` — 全量生命周期日志，永不清空

通过 `read_current_events()` 读取当前会话的事件。

**竞争条件警告：** Claude Code 默认并行运行多个 `SubagentStop` hook。如果两个 hook 同时读写 `metrics_current.jsonl`，会导致偶发的 `JSONDecodeError` 崩溃。这正是 `on_subagent_stop.py` 存在的原因——它将 `log_subagent` 和 `check_worker_report` 串行化在同一个进程内。如果你要新增 `SubagentStop` hook，请将其作为串行调用加入 `on_subagent_stop.py`，而不是注册为独立 hook。

### 状态（可变计数器）

使用 `hooks/metrics/state` 中的 `state.get`、`state.put` 和 `state.increment` 管理会话期间会变化的值（拦截次数、标志位等）：

```python
from metrics import state

count = state.increment("my_counter")   # 返回新值
state.put("my_flag", True)
value = state.get("my_flag", default=False)
```

状态存储在 `.godotmaker/state.json` 中，在每次 `SessionStart` 时重置。

---

## 注册新 Hook

1. 在 `hooks/<my_hook>.py` 创建 hook 脚本。

2. 将它添加到需要触发该 hook 的 runner 入口：Claude Code 使用
   `agent-runtimes/claude-code/config/settings.json`，Codex 使用
   `agent-runtimes/codex/config/hooks.json`，OpenCode 使用
   `agent-runtimes/opencode/plugins/godotmaker-hooks.js`。

   ```json
   {
     "hooks": {
       "PreToolUse": [
         {
           "matcher": "Write|Edit",
           "hooks": [
             {"type": "command", "command": "python .godotmaker/hooks/check_file_permissions.py"},
             {"type": "command", "command": "python .godotmaker/hooks/my_hook.py"}
           ]
         }
       ]
     }
   }
   ```

   同一事件+matcher 的 hook 按列出的顺序执行。如果前面的 hook 拦截了操作，该事件后续的 hook 可能不会运行。

3. 发布到测试项目并触发相关操作进行验证：

   ```bash
   python tools/publish.py /path/to/scratch-game
   ```

4. 在 `tests/hooks/test_my_hook.py` 下编写单元测试。测试模式见 [测试](testing.md)。
