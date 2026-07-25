# 素材工具

GodotMaker 通过几个小型 Python 辅助脚本生成和处理 2D 美术资源。`/gm-asset` 会自动调度主流程工具。手动调用只用于调试单个 source、单个动作 sheet 或单次 curation 决策。

主流程工具：

1. `asset_source_generate.py`
2. `asset_layout_guide.py`
3. `asset_action_process.py`
4. `asset_sheet_process.py`
5. `asset_curation_select.py`
6. `asset_output_path.py`
7. `asset_stable_entry.py`
8. `asset_generation_index.py`
9. `asset_assets_md_update.py`

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

## asset_output_path.py

`asset_output_path.py` 是稳定输出目录 `assets/generated/<production_family>/<asset_id>/` 的唯一权威。一个素材所有可被 worker 消费的文件都放在这里，因此重新生成会就地覆盖，不会漂移到带时间戳或 `v2` 的路径。

手动入口：

```bash
python tools/asset_output_path.py --family <production_family> --asset-id <asset_id>
python tools/asset_output_path.py --entry <entry.json> --project-root . --check-files
```

## asset_stable_entry.py

`asset_stable_entry.py` 校验一个 v1 stable entry，并把它序列化到 `.godotmaker/asset-generation/entries/<tag>/<asset_id>.json`。entry 只保存稳定身份加上 `production_family`、`source_layout`、可选的最小 `godot_artifact` 和 `processing_status`，不保存其他字段。

手动入口：

```bash
python tools/asset_stable_entry.py <entry_draft.json> --project-root . --write --check-files
```

## asset_generation_index.py

`asset_generation_index.py` 拥有位于 `.godotmaker/asset-generation/manifest.json` 的 pointer-only root index。它只保存身份和每个素材的一个 `entry_path`，绝不复制 entry 内容。

手动入口：

```bash
python tools/asset_generation_index.py --project-root . \
  --entry-file .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
python tools/asset_generation_index.py --project-root . --check-entries
```

把完整 entry 内容存在 `assets` 键下的旧 `runtime_artifact` manifest 会被拒绝并提示重新生成；不提供迁移或兼容读取。

## asset_assets_md_update.py

`asset_assets_md_update.py` 会根据已注册的 stable entry 更新 ASSETS.md 行。它先重新校验 entry 和被引用的文件，所以只有素材确实存在于磁盘上时行才会变成 `generated`；行里只记录 entry 指针，不复制任何路径。

手动入口：

```bash
python tools/asset_assets_md_update.py \
  --entry-file .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
```

## 手动调用这些脚本

大多数情况下不需要直接运行这些脚本。`/gm-asset` 会根据 `ASSETS.md` 和 source-generation manifest 自动调度它们。

主要手动场景：

1. 用调整过的 spec 重新生成某一个 source 图片。
2. 为固定网格 source 创建一个 layout guide。
3. 调试动画输出时单独处理一个角色动作 sheet。
4. 在完整运行 `/gm-asset` 前试验不同的提供商、尺寸或宽高比。
5. 调试 extraction 时单独处理一个 source sheet。
6. 把某个 extracted candidate 选入运行时素材路径。
7. 打印或校验某个素材的稳定输出目录。
8. 校验并注册一个 stable entry 及其 root-index 指针。

如果想更新 `/gm-evaluate` 用于对比的视觉目标，请重新运行 `/gm-asset`，不要直接编辑已生成的图片。
