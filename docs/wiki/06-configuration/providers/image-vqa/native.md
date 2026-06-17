# native image and VQA provider

`native` means the active coding-agent runtime supplies the image or vision
capability. It is not an API provider.

## Project config

```yaml
asset_image_model: native
vqa_model: native
```

## Runtime support

| Runtime | Native image generation | Native VQA |
|---|---|---|
| Claude Code | Only when the active host provides it | Supported through runtime image inspection |
| Codex | Supported when the active Codex host provides it | Supported when the active Codex host provides it |
| OpenCode | Unsupported | Unsupported |

For OpenCode projects, choose `codex`, `gemini:<model>`, `openai:<model>`, or
`grok:<model>` for image generation, and choose `codex`, `gemini:<model>`, or
`openai:<model>` for VQA.
