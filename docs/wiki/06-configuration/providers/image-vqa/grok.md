# Grok image provider

Use Grok when you want API-backed image generation through xAI.

## Project config

```yaml
asset_image_model: grok:grok-imagine-image
```

Grok is used for asset image generation only. Use `native`, `codex`,
`gemini:<model>`, or `openai:<model>` for VQA.

## Setup

1. Set your API key:

```bash
export XAI_API_KEY=...
```

2. Install the Python package:

```bash
pip install xai-sdk
```

3. Run `python tools/check_env.py`.
