# 素材工具

GodotMaker 通过几个小型 Python 辅助脚本生成和处理 2D 美术资源。`/gm-asset` 会自动调度这些脚本；你也可以手动运行它们来测试单个 source、抠图步骤或 sheet 处理步骤。

## asset_source_generate.py

`asset_source_generate.py` 会根据 JSON spec 生成 API 后端 source 图片，支持 Gemini、OpenAI 和 xAI Grok 选择器。运行时原生的 `native` / `codex` 图片生成由 `/gm-asset` 选择，不由这个脚本调用。

带提供方前缀的选择器需要对应 key：Gemini 需要 `GOOGLE_API_KEY` / `GEMINI_API_KEY`，OpenAI 需要 `OPENAI_API_KEY`，Grok 需要 `XAI_API_KEY`。要设置 `/gm-asset` 使用哪个提供方，请在 [`../06-configuration/project-config.md`](../06-configuration/project-config.md) 中配置 `asset_image_model`。

### 生成 source 图片

先写 spec：

```json
{
  "asset_id": "player_canonical",
  "model": "gemini:gemini-3.1-flash-image-preview",
  "prompt": "top-down player character, blue outfit, centered on a solid green background",
  "prompt_path": ".godotmaker/asset-generation/prompts/player_canonical.txt",
  "source_path": ".godotmaker/asset-generation/sources/player_canonical_source.png",
  "size": "1K",
  "aspect_ratio": "1:1",
  "reference_images": [],
  "report_path": ".godotmaker/asset-generation/reports/player_canonical_source.json"
}
```

执行：

```bash
python tools/asset_source_generate.py \
  --spec .godotmaker/asset-generation/specs/player_canonical.json
```

脚本会写入 prompt 文件、source 图片和可选 report。最终运行时素材由后续资产管线选择和 finalize。

## rembg_matting.py

`rembg_matting.py` 用于去除图片的纯色背景，输出带透明背景的 PNG 文件。

```bash
# 单张图片
python tools/rembg_matting.py assets/sprites/enemy_raw.png -o assets/sprites/enemy.png

# 批量处理
python tools/rembg_matting.py --batch raw_frames/ -o clean_frames/

# 生成预览
python tools/rembg_matting.py assets/sprites/enemy_raw.png --preview
```

工具使用神经网络识别主体，结合颜色抠图清理边缘。可以用 `-m trust`、`-m adapt` 或 `-m color` 强制指定模式。

如果有支持 CUDA 的 NVIDIA GPU，会自动启用 GPU 加速。在 CPU 上运行较慢，但同样可用。

## 手动调用这些脚本的场景

大多数情况下不需要直接运行这些脚本。`/gm-asset` 会根据 `ASSETS.md` 和 source-generation manifest 自动调度它们。

需要手动调用的主要场景：

- 你想用调整过的 spec 重新生成某一个 source 图片。
- 在完整运行 `/gm-asset` 之前，你想先试验不同的提供商、尺寸或宽高比。
- 你拿到了外部提供的 source 图片，需要去除纯色背景。
- 你在调试 extraction 时需要单独处理一个 source sheet。

如果你想更新 `/gm-evaluate` 用于对比的视觉目标，请重新运行 `/gm-asset`，而不是直接修改已生成的图片。
