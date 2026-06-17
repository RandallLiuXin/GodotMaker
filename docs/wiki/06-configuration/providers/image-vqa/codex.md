# codex image and VQA provider

`codex` means Codex supplies image generation or image inspection even when the
main project runner is not Codex.

## Project config

```yaml
asset_image_model: codex
vqa_model: codex
```

## Setup

1. Install Codex and sign in.
2. Make sure the `codex` command is on `PATH`.
3. Run `python tools/check_env.py`.

This provider does not require an image API key. It does require the active
Codex environment to expose the needed image or vision capability.
