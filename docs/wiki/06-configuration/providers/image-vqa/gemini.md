# Gemini image and VQA provider

Use Gemini when you want API-backed image generation or visual QA.

## Project config

```yaml
asset_image_model: gemini:gemini-3.1-flash-image-preview
vqa_model: gemini:gemini-2.5-flash
```

## Setup

1. Create a Gemini API key.
2. Set one of:

```bash
export GOOGLE_API_KEY=...
export GEMINI_API_KEY=...
```

3. Install the Python package:

```bash
pip install google-genai
```

4. Run `python tools/check_env.py`.
