# 检查运行环境

`check_env.py` 用于确认你的机器已正确配置，可以运行 GodotMaker。遇到任何异常时都可以执行它。

```bash
python tools/check_env.py
```

一切正常时，输出末尾会显示：

```
All required checks passed! Ready to use GodotMaker.
```

如果有项目缺失，你会看到一份失败检查列表以及每项的修复建议。

## 检查内容

### Git

- 已安装 Git 2.30 或更高版本。
- 已设置 `git user.name` 和 `git user.email`（`/gm-scaffold` 及 worktree 系统创建提交时需要用到）。

### Python

- 运行本脚本的 Python 版本为 3.10 或更高。
- 已安装核心包：`requests`、`pillow`。
- 根据 `.godotmaker/config.yaml` 检查提供方包：Gemini 需要 `google-genai`，OpenAI 需要 `openai`，Grok 图片生成需要 `xai-sdk`。Wan 使用标准库 HTTP 客户端；选中后还要求 `DASHSCOPE_API_KEY` 与显式 `DASHSCOPE_REGION`。

### Godot E2E（Python 包）

- `godot-e2e` Python 包可以被**运行本脚本的那个解释器**导入，而不仅仅是 PATH 上存在某个 `godot-e2e` 命令。

这里只检查 Godot E2E 的 Python 一侧。项目内的 `addons/godot_e2e/` addon 是另一个依赖，由 [`check_project.py`](check-project.md) 负责——两者互不代表，缺少其中一个不能说明另一个的状态。

由于 PATH 上的 `godot-e2e` 命令属于当初安装它的那个 Python 环境，检查会报告它实际使用的解释器、`sys.prefix`、`VIRTUAL_ENV`，以及 PATH 命令（如果存在）的位置：

```
--- Godot E2E (Python package) ---
  interpreter: /home/you/game/.venv/bin/python
  python version: 3.11.5
  sys.prefix: /home/you/game/.venv (virtualenv)
  VIRTUAL_ENV: not set
  godot-e2e command on PATH: /usr/local/bin/godot-e2e
  the godot-e2e command at /usr/local/bin/godot-e2e is not part of /home/you/game/.venv/bin/python; ...
  next: /home/you/game/.venv/bin/python -m pip install godot-e2e
[FAIL] Python package 'godot-e2e' missing for /home/you/game/.venv/bin/python; a godot-e2e command exists at /usr/local/bin/godot-e2e but belongs to another Python environment — install it into that interpreter: /home/you/game/.venv/bin/python -m pip install godot-e2e
```

单独运行 `python tools/e2e_env.py` 可以得到同样的报告，并额外给出通过已验证解释器运行测试套件的确切命令。两者每次都会重新探测，因此修正解释器或虚拟环境后失败会立刻消失，不会复用此前的判定结果。

### Node.js

- 已安装 Node.js 18 或更高版本（通过 `npx` 运行 `godot-mcp` 时需要）。
- `npx` 在 PATH 中可用（随 Node.js 一起安装）。

### Godot

- Godot 4.5 或更高版本可通过 PATH 中的 `godot` 或 `godot4` 命令访问。

如果 Godot 不在 PATH 中，这项检查会显示警告而非硬性失败——你仍可以在运行 `publish.py` 时手动输入可执行文件的完整路径，它会被保存到 `.claude/godotmaker.yaml` 供后续使用。

### 所选 coding agent

- Claude Code 项目会检查 `claude` 是否已安装。
- Codex 项目会检查 `codex` 是否已安装、`.agents` runtime tree 是否存在，以及 `godot` MCP server 是否已配置。
- OpenCode 项目会检查 `opencode` 是否已安装、`.opencode` runtime tree 和 hook adapter 是否存在，以及 `godot` MCP server 是否已配置。

### API 密钥

| 密钥 | 状态 | 用途 |
|-----|--------|---------|
| `GOOGLE_API_KEY` 或 `GEMINI_API_KEY` | 选中时必填 | Gemini 图片生成或 VQA |
| `OPENAI_API_KEY` | 选中时必填 | OpenAI 图片生成或 VQA |
| `XAI_API_KEY` | 选中时必填 | xAI Grok 图片生成 |


API 后端 selector 在缺少对应 key 时会失败。`asset_image_model: native` 对 Codex 会通过，对 Claude Code 会给出警告，因为检查工具无法证明 Claude 侧一定有原生生图能力。OpenCode 项目如果使用 `native` 生图或 `native` VQA 会失败，直到你把这些字段改成 `codex` 或 API 后端 selector。Claude Code 或 OpenCode 项目使用 `asset_image_model: codex` 时，需要 `codex` CLI 位于 PATH 中。

检查工具还会验证被选中提供方的 Python 包能否正常导入，从而捕获单靠版本号检查无法发现的安装问题。

## 读懂输出结果

每行以以下三种标记之一开头：

```
[PASS] Git 2.43.0 (>= 2.30)
[FAIL] Package 'google-genai' missing. Run: pip install google-genai
[WARN] XAI_API_KEY not set (optional, cheaper image generation)
```

`[WARN]` 表示可选项——不影响 GodotMaker 的使用。`[FAIL]` 表示阻断性问题。

输出末尾会汇总所有失败项，方便你一次性全部修复：

```
========================================
Total: 14 checks
  PASS: 12
  FAIL: 1
  WARN: 1

Failed checks:
  - Package 'google-genai' missing. Run: pip install google-genai

Fix the above issues before using GodotMaker.
```

## 退出码

| 退出码 | 含义 |
|------|---------|
| 0 | 所有必填检查通过（有警告也没关系） |
| 1 | 一项或多项必填检查失败 |

脚本和 CI 流水线可以依靠这个退出码来决定是否继续执行后续步骤。

## 刚开始上手？

参阅[安装指南](../01-getting-started/installation.md)，按步骤完成所有前置条件的配置，再运行 `check_env.py`。
