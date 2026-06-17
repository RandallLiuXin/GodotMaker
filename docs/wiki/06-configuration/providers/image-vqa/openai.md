# OpenAI image and VQA provider

Use OpenAI when you want API-backed image generation or visual QA.

## Project config

```yaml
asset_image_model: openai:gpt-image-2
vqa_model: openai:gpt-5.5
```

## Setup

1. Set your API key:

```bash
export OPENAI_API_KEY=...
```

2. Install the Python package:

```bash
pip install openai
```

3. Run `python tools/check_env.py`.
