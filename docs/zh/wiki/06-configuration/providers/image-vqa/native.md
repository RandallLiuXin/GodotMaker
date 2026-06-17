# native 图片和 VQA provider

`native` 表示由当前 coding-agent runtime 提供图片或视觉能力。它不是 API provider。

## 项目配置

```yaml
asset_image_model: native
vqa_model: native
```

## Runtime 支持情况

| Runtime | 原生生图 | 原生 VQA |
|---|---|---|
| Claude Code | 只有当前宿主提供时才支持 | 通过 runtime 图片检查路径支持 |
| Codex | 当前 Codex 宿主提供时支持 | 当前 Codex 宿主提供时支持 |
| OpenCode | 不支持 | 不支持 |

OpenCode 项目请为生图选择 `codex`、`gemini:<model>`、`openai:<model>` 或
`grok:<model>`，为 VQA 选择 `codex`、`gemini:<model>` 或 `openai:<model>`。
