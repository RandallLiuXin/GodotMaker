# Grok 图片 provider

当你希望通过 xAI API 生成图片时，可以使用 Grok。

## 项目配置

```yaml
asset_image_model: grok:grok-imagine-image
```

Grok 只用于素材图片生成。VQA 请使用 `native`、`codex`、`gemini:<model>` 或
`openai:<model>`。

## 配置步骤

1. 设置 API key：

```bash
export XAI_API_KEY=...
```

2. 安装 Python 包：

```bash
pip install xai-sdk
```

3. 运行 `python tools/check_env.py`。
