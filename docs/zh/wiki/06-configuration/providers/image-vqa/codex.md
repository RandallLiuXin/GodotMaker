# codex 图片和 VQA provider

`codex` 表示由 Codex 提供图片生成或图片检查能力，即使当前项目 runner 不是 Codex。

## 项目配置

```yaml
asset_image_model: codex
vqa_model: codex
```

## 配置步骤

1. 安装 Codex 并登录。
2. 确认 `codex` 命令位于 `PATH` 中。
3. 运行 `python tools/check_env.py`。

这个 provider 不需要图片 API key，但需要当前 Codex 环境实际暴露所需的图片或视觉能力。
