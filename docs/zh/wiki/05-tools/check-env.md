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
- 根据 `.godotmaker/config.yaml` 检查提供方包：Gemini 需要 `google-genai`，OpenAI 需要 `openai`，Grok 图片生成需要 `xai-sdk`。

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
