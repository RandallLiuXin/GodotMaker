# 测试

请在官方支持基线 Python 3.10+、Node.js 22+ 和 Godot 4.5+ 上运行测试。
`tests/` 覆盖 hook、asset/runtime 合同、publish 与迁移工具、项目检查和端到端
流水线。用以下命令运行完整测试套件：

```bash
python -m pytest tests/ -x -q
```

`-x` 参数在第一次失败时立即停止。去掉它可以一次看到所有失败。`pyproject.toml` 设置了 `pythonpath = ["hooks"]`，使 hook 测试中的 `from metrics import ...` 无需任何安装步骤即可解析。

---

## 测试目录结构

```
tests/
├── assets/                               Asset family 与 compiler 合同
├── agent_runtimes/                       Runtime adapter 合同
├── hooks/                                Hook 行为与共享 helper
├── tools/                                CLI 与发布测试
└── test_*.py                             跨层与流水线合同
```

测试模块按所证明的行为分组，不维护生产文件与测试文件一一对应的镜像。需要当前
inventory 时，请使用 `pytest --collect-only` 或 `rg --files tests`。
`test_pipeline_e2e.py` 在较粗粒度上验证发布 → 会话启动 → 角色执行序列。

---

## 为新 Hook 添加测试

Hook 测试遵循统一的模式：构建一个合成的 JSON payload，以子进程方式运行 hook，断言其是否产生了拦截。

### 工具函数

`tests/hooks/helpers.py` 提供了每个 hook 测试都会用到的四个工具函数：

**`run_hook(script_name, input_data)`** — 以子进程方式启动 hook 脚本，通过 stdin 以 JSON 格式发送 `input_data`，返回 `(stdout_text, exit_code, parsed_json)`。脚本在相对于项目根目录的 `hooks/` 中定位。超时时间为 10 秒。

**`is_blocked(parsed)`** — 检查解析后的 JSON 响应是否为拦截决策。同时处理 PreToolUse 格式（`hookSpecificOutput.permissionDecision == "deny"`）和 Stop/SubagentStop 格式（`decision == "block"`）。

**`write_completed_roles(roles)`** — 向 `.godotmaker/stage.jsonl` 写入角色完成事件。接受角色名字符串列表、`{role: timestamp}` 字典，或原始事件字典列表。

**`write_current_role(role)`** — 向 `.godotmaker/current_role` 写入指定的角色名。

**`write_metrics(events)`** — 向 `.godotmaker/metrics_current.jsonl` 写入指定的事件列表。

**`cleanup_metrics()`** — 完整删除 `.godotmaker/` 目录。在 `teardown_method` 中调用，保持测试之间相互隔离。

### 示例：一个 Hook 测试

```python
import os
import pytest
from helpers import (
    run_hook, is_blocked,
    write_current_role, write_completed_roles, cleanup_metrics
)


class TestMyHook:
    def setup_method(self):
        # 搭建 hook 所期望的文件系统状态
        write_completed_roles(["scaffold", "gdd"])
        write_current_role("build")

    def teardown_method(self):
        cleanup_metrics()

    def test_allows_valid_write(self):
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "src/player.gd", "content": "extends Node"},
            "agent_id": "worker-1"
        }
        stdout, code, parsed = run_hook("my_hook.py", event)
        assert not is_blocked(parsed)

    def test_blocks_protected_path(self):
        event = {
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "PLAN.md", "content": "# Plan"},
            "agent_id": "worker-1"
        }
        stdout, code, parsed = run_hook("my_hook.py", event)
        assert is_blocked(parsed)
```

关键要点：
- 每个测试自包含：在 `setup_method` 中搭建环境，在 `teardown_method` 中清理。
- 使用 `write_completed_roles` 控制 `stage.jsonl` 中哪些角色已完成。
- 使用 `write_current_role` 控制权限检查时的活跃角色。
- `is_blocked` 处理两种响应格式，不要直接检查原始 JSON 结构。

---

## 为新工具添加测试

工具测试使用标准的 pytest 模式。`tests/tools/conftest.py` 提供共享 fixture。

```python
from pathlib import Path


def test_my_tool_feature(tmp_path):
    # 创建最小化的 fixture 文件
    (tmp_path / "project.godot").write_text("[gd_resource]")

    # 直接导入并调用函数
    import sys
    sys.path.insert(0, str(Path(__file__).parent.parent.parent / "tools"))
    from my_tool import my_function

    result = my_function(tmp_path)
    assert result == expected_value
```

使用 `tmp_path`（pytest 内置 fixture）实现文件系统隔离。如果工具调用了子进程，使用 `unittest.mock.patch` 进行 mock。如果工具需要网络调用（例如 API key 检查），为测试添加标记：

```python
import pytest

@pytest.mark.network
def test_requires_api():
    ...
```

在本地跳过网络测试：

```bash
python -m pytest tests/ -m "not network" -x -q
```

---

## Pre-commit 与 CI

仓库的 pre-commit hook 会运行快速的 staged 检查：对 staged Python 文件做 lint，检查用户文档是否同步更新中文镜像，并在本地工具已安装时扫描密钥。测试在每个 Pull Request 时通过 CI 运行。提交 PR 前在本地跑完整套件是默认期望：

```bash
python -m pytest tests/ -x -q
```

如果你在新增一个 hook，还需运行共享引用发布测试，确认 manifest 有效：

```bash
python -m pytest tests/tools/test_publish_shared.py -q
```
