# 素材工具

GodotMaker 通过几个小型 Python 辅助脚本生成和处理 2D 美术资源。`/gm-asset` 会自动调度主流程工具。手动调用只用于调试单个 source、单个动作 sheet 或单次 curation 决策。

主流程工具：

1. `asset_source_generate.py`
2. `asset_layout_guide.py`
3. `asset_action_process.py`
4. `asset_action_manifest_entry.py`
5. `asset_sheet_process.py`
6. `asset_curation_select.py`
7. `asset_curation_manifest_entry.py`

可选 curation 工具：

1. `rembg_matting.py`

## asset_source_generate.py

`asset_source_generate.py` 会根据 JSON spec 生成 API 后端 source 图片，支持 Gemini、OpenAI 和 xAI Grok selector。运行时原生的 `native` 和 `codex` 图片生成由 `/gm-asset` 选择，不由这个脚本调用。

带提供方前缀的 selector 需要对应 key：Gemini 需要 `GOOGLE_API_KEY` / `GEMINI_API_KEY`，OpenAI 需要 `OPENAI_API_KEY`，Grok 需要 `XAI_API_KEY`。要设置 `/gm-asset` 使用哪个提供方，请在 [`../06-configuration/project-config.md`](../06-configuration/project-config.md) 中配置 `asset_image_model`。

手动入口：

```bash
python tools/asset_source_generate.py --spec <spec.json>
```

spec 包含 asset id、model selector、prompt、prompt path、source path、尺寸、宽高比、reference images 和 report path。

## asset_layout_guide.py

`asset_layout_guide.py` 会为固定网格 source 图片创建 layout guide。适用于 UI component sheet、icon pack、compact prop pack 和 action sheet。

手动入口：

```bash
python tools/asset_layout_guide.py \
  --out <guide.png> \
  --rows <rows> \
  --cols <cols> \
  --labels <labels>
```

guide 用于约束 image generation 的 slot 数量、居中和安全边距。它不是运行时美术资源。

## rembg_matting.py

`rembg_matting.py` 是可选 curation 工具，用于在 source sheet 处理前移除纯色背景。

手动入口：

```bash
python tools/rembg_matting.py <input.png> -o <output.png>
python tools/rembg_matting.py --batch <input_dir> -o <output_dir>
python tools/rembg_matting.py <input.png> --preview
```

工具使用神经网络（BiRefNet）识别主体，并结合颜色 matting 清理边缘。可以用 `-m trust`、`-m adapt` 或 `-m color` 指定模式。

如果有支持 CUDA 的 NVIDIA GPU，会自动启用 GPU 加速。在 CPU 上会更慢，但仍可使用。

## asset_sheet_process.py

`asset_sheet_process.py` 会把非角色 2D source sheet 拆成裁剪后的候选对象，并写出 curation report。它支持透明 sheet，也支持通过 `--background magenta` 处理纯 `#FF00FF` 背景 sheet。

它适用于 icon pack、小型道具包、UI 组件 sheet 和其他非角色 source sheet。

必须决定：

1. `--grid <COLSxROWS>`
2. `--names <comma-separated names>`
3. 对象已经分离时使用 `--snap-mode autoslice`
4. 严格 cell 网格使用 `--snap-mode grid`
5. 紧凑 UI、icon、prop cell 中有零散碎片时使用 `--component-mode largest`

手动入口：

```bash
python tools/asset_sheet_process.py \
  --source <source.png> \
  --out-dir <curation_dir> \
  --grid <COLSxROWS> \
  --names <names> \
  --snap-mode <autoslice|grid> \
  --report <report.json>
```

## asset_action_process.py

`asset_action_process.py` 用于处理角色、敌人、NPC、召唤物和动画道具的动作 source。它会写出规范化 frame PNG、`sheet-transparent.png`、`animation.gif`、`pipeline-meta.json` 和中间 curation report。

必须决定：

1. body-only 角色动作使用 `--kind body`
2. 分离式特效使用 `--kind fx`
3. `--grid <COLSxROWS>`
4. `--names <comma-separated frame names>`
5. grounded body action 使用 `--align feet` 或 `--align bottom`
6. floating action 和 detached effect 使用 `--align center`
7. 后续 body action 使用 `--scale-reference-metadata <pipeline-meta.json>`

这个工具会拒绝碰到 source cell 边缘的动作帧。`--final-dir` 和 `--final-prefix` 只会把处理后的 frames 和 delivery grid sheet 复制到运行时路径；它们不会组装 mixed atlas 或 row strip。

手动入口：

```bash
python tools/asset_action_process.py \
  --source <action_source.png> \
  --out-dir <processed_dir> \
  --grid <COLSxROWS> \
  --names <frame_names> \
  --kind <body|fx> \
  --final-dir <runtime_dir> \
  --final-prefix <asset_id>
```

后续 body action 追加：

```bash
--scale-reference-metadata <accepted_action_pipeline_meta.json>
```

## asset_action_manifest_entry.py

`asset_action_manifest_entry.py` 会把一个已处理动作的 `pipeline-meta.json` 和对应的 `character_action_source` entry 转换成 `character_frame_output` manifest entry。

手动入口：

```bash
python tools/asset_action_manifest_entry.py \
  --metadata <processed_dir>/pipeline-meta.json \
  --source-entry <character_action_source_entry.json> \
  --asset-id <frame_output_asset_id> \
  --project-root . \
  --out <frame_output_entry.json>
```

生成的 entry 继续交给 `asset_generation_manifest_update.py` upsert。

## asset_curation_select.py

`asset_curation_select.py` 会从 curation report 中选择一个 candidate，并 finalize 到运行时素材路径。

手动入口：

```bash
python tools/asset_curation_select.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --final-path <final_path> \
  --asset-id <final_asset_id> \
  --project-root .
```

工具会把 report 状态更新为 `selected`，记录 candidate 的 final path，并输出与 `asset_image_finalize.py` 相同的 finalize metadata。

## asset_curation_manifest_entry.py

`asset_curation_manifest_entry.py` 会把一个已选中的 curation candidate 和它对应的 source-sheet manifest entry 转换成已校验的运行时 manifest entry。

手动入口：

```bash
python tools/asset_curation_manifest_entry.py \
  --report <report.json> \
  --source-entry <source_sheet_entry.json> \
  --candidate <candidate_id_or_name> \
  --asset-id <final_asset_id> \
  --project-root . \
  --out <final_asset_entry.json>
```

生成的 entry 继续交给 `asset_generation_manifest_update.py` upsert。

## 手动调用这些脚本

大多数情况下不需要直接运行这些脚本。`/gm-asset` 会根据 `ASSETS.md` 和 source-generation manifest 自动调度它们。

主要手动场景：

1. 用调整过的 spec 重新生成某一个 source 图片。
2. 为固定网格 source 创建一个 layout guide。
3. 调试动画输出时单独处理一个角色动作 sheet。
4. 从 action metadata 生成一个 character frame-output manifest entry。
5. 在完整运行 `/gm-asset` 前试验不同的提供商、尺寸或宽高比。
6. 在 source sheet curation 前移除纯色背景。
7. 调试 extraction 时单独处理一个 source sheet。
8. 把某个 extracted candidate 选入运行时素材路径。
9. 从已选中的 curation candidate 生成一个运行时 manifest entry。

如果想更新 `/gm-evaluate` 用于对比的视觉目标，请重新运行 `/gm-asset`，不要直接编辑已生成的图片。
