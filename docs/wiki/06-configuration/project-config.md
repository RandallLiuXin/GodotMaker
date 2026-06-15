# Project config

`.godotmaker/config.yaml` is per-project: it selects the agent runtime, role models, visual QA model, and asset generation model for a game project. It lives inside the project folder, so different games can use different settings.

## How it gets created

For normal users, `godotmaker-cli` creates `.godotmaker/config.yaml` during the first project publish. The preflight panel points to the file so you can edit model and provider settings before continuing.

Framework developers and manual-mode users can still create the same file with `python tools/publish.py <project>`. On subsequent publishes the file is left untouched except for the `agent` field, which is updated to the selected runtime.

## Common fields

**`agent`** — selected coding-agent runtime, such as `claude-code` or `codex`.

**`worker_model`** — which Claude model writes game code. Defaults to `sonnet`; set it to `opus` for games that need heavier implementation reasoning.

**`verifier_model`**, **`reviewer_model`**, **`analyst_model`**, **`auditor_model`**, **`decomposer_model`** — role model defaults for validation, review, image analysis, audit, and GDD decomposition.

**`vqa_model`** — primary visual QA selector. Supported values are `native`, `codex`, `gemini:<model>`, and `openai:<model>`. `native` means the active agent runtime inspects the images directly. `codex` means Codex supplies the image inspection. API-backed selectors run `visual_qa.py`.

**`vqa_fallback_model`** — fallback when the primary VQA backend is unavailable. Supported values are `native`, `codex`, and `none`.

**`asset_image_model`** — image generation selector for `/gm-asset`. Supported values are `native`, `codex`, `gemini:<model>`, `openai:<model>`, and `grok:<model>`. `native` is handled by the active agent runtime. `codex` is handled by Codex native image generation. API-backed selectors run `tools/asset_source_generate.py --spec <spec.json>`; the script rejects runtime providers.

**`asset_producer_model`** — model used by generated-art producer subagents. Defaults to `sonnet`.

The default config looks like this:

```yaml
# GodotMaker project configuration
# Edit these values to customize behavior
# Deployed to .godotmaker/config.yaml by publish script

agent: claude-code

vqa_model: native
vqa_fallback_model: native

asset_image_model: native

asset_producer_model: sonnet
worker_model: sonnet
verifier_model: sonnet
reviewer_model: sonnet
analyst_model: sonnet
auditor_model: sonnet
decomposer_model: sonnet
```

## Runtime-native image generation

`native` is not an API provider. It means the active agent runtime supplies image inspection or image generation.

The template uses native image inspection and native image generation by default.

For Codex projects, `asset_image_model: native` maps to Codex native image generation when the host exposes that capability. For Claude Code projects, `native` requires a Claude-side native image tool. If no native path is available, `/gm-asset` must stop and ask you to configure a supported provider or switch to an API-backed selector.

For a Claude Code project that should use Codex image generation:

```yaml
asset_image_model: codex
```

This selects Codex as the image-generation provider. It requires Codex CLI on
PATH and does not require an image API key.

## API keys

Provider-prefixed selectors require the matching API key:

| Selector | Required key |
|---|---|
| `gemini:<model>` | `GOOGLE_API_KEY` or `GEMINI_API_KEY` |
| `openai:<model>` | `OPENAI_API_KEY` |
| `grok:<model>` | `XAI_API_KEY` |

Asset generation does not silently fall back when a key is missing. VQA can fall back only through the explicit `vqa_fallback_model` setting.

## How to change a setting

Open `.godotmaker/config.yaml` and change the value after the colon. For example, to switch the project runner:

```yaml
agent: codex
```

Launch-time `--agent` still wins for that run:

```bash
godotmaker-cli --agent claude-code
godotmaker-cli --agent codex
```

To use Codex image generation:

```yaml
asset_image_model: codex
```

To use OpenAI for API-backed image generation:

```yaml
asset_image_model: openai:gpt-image-2
```

The next `/gm-*` command picks up the new value. A command already running will not see changes until the next session or stage invocation.

## About `.claude/settings.json`

Claude Code projects also have `.claude/settings.json`, which registers GodotMaker hook scripts. It is framework-managed; running `python tools/publish.py --force <project>` republishes it if hooks stop firing after an upgrade.
