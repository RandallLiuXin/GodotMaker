# 素材工具

GodotMaker 通过几个小型 Python 辅助脚本生成和处理 2D 美术资源。`/gm-asset` 会自动调度主流程工具。手动调用只用于调试单个 source、单个动作 sheet 或单次 curation 决策。

主流程工具：

1. `asset_source_generate.py`
2. `asset_layout_guide.py`
3. `asset_action_process.py`
4. `asset_sheet_process.py`
5. `asset_curation_select.py`
6. `asset_action_entry_draft.py`
7. `asset_curation_entry_draft.py`
8. `asset_finalize_entry_draft.py`
9. `asset_output_path.py`
10. `asset_stable_entry.py`
11. `asset_generation_index.py`
12. `asset_assets_md_update.py`
13. `asset_atlas_assemble.py`
14. `asset_runtime_resolver.py`
15. `asset_compact_prop_pack_entry_draft.py`
16. `asset_scene_prop_set_entry_draft.py`
17. `asset_ui_card_entry_draft.py`
18. `asset_tileset_entry_draft.py`
19. `asset_bundle_rows.py`

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

1. `--names <comma-separated names>`
2. 独立对象已经分离时使用 `--snap-mode autoslice`
3. 严格 cell 网格使用 `--snap-mode grid --grid <COLSxROWS>`
4. 紧凑 UI、icon、prop cell 中有零散碎片时使用 `--component-mode largest`

手动入口：

```bash
python tools/asset_sheet_process.py \
  --source <source.png> \
  --out-dir <curation_dir> \
  --names <names> \
  --snap-mode <autoslice|grid> \
  --report <report.json>
```

只在 `--snap-mode grid` 中传入 `--grid <COLSxROWS>`。Autoslice 按从上到下、
从左到右输出独立区域；`--names` 数量与检测区域数量不一致时会拒绝语义映射。

使用 `--processed-out <transparent-sheet.png>` 可保留清理后的 RGBA source sheet
供审计。Autoslice 报告名称数量不匹配时不会写出该文件，避免未绑定的 sheet 被
误认为有效的生产产物。

使用 `--background magenta` 时，`--magenta-threshold`（默认 `60`）是严格的全图清理半径；传入 `0` 可将封闭区域清理限制为精确的 `#FF00FF`。`--magenta-edge-threshold`（默认 `220`）不是删除半径，只用于限制后续能由键色和相邻前景像素一致解释的边缘混色反解。这样会保留独立的紫色、蓝紫色精灵与细线，并将已验证的 spill 转为正确颜色的半透明边缘。

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

## asset_action_entry_draft.py

`asset_action_entry_draft.py` 会把一个已处理动作的 `pipeline-meta.json` 转换成 action support metadata 和一个 v1 stable-entry draft。它是 action 路径上的机械关卡：frame count 与实际帧列表一致、`edge_touch_frames` 必须为空、scale reference 必须已记录，以及所有运行时路径必须落在该素材的稳定输出目录内。

手动入口：

```bash
python tools/asset_action_entry_draft.py \
  --metadata <processed_dir>/pipeline-meta.json \
  --asset-id <asset_id> \
  --tag <tag> \
  --production-family character-bundle \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

draft 停在 `processing_status: source_ready`，不带 `godot_artifact`。`grid_sheet` 只有在原生 compiler 产出 `SpriteFrames` 且 L0-L4 runner 校验通过后，才可以被 worker 消费。

加上 `--request` 会切换到 `character-bundle` 或动画 `fx-bundle` 的 bundle 模式：编译出一个共享的 `SpriteFrames`，写入 `compiled` entry，并把 build fingerprint 记录到 support metadata。之后带 `--result <result.json>` 再跑一次，会把同一个 entry 提升为 `ready`。提升过程不会重新编译——它从磁盘重算 fingerprint 并要求完全一致，因此一个针对旧构建通过 L0-L4 的 result，无法提升现在占据同一批身份派生路径的产物。

## asset_curation_entry_draft.py

`asset_curation_entry_draft.py` 会把一个已选中的 curation candidate 转换成 v1 stable-entry draft。它要求指定的 candidate 存在、不歧义、且状态确实是 `selected`，report 的 selected/rejected 计数自洽，finalize 后的路径落在该素材的稳定输出目录内。

手动入口：

```bash
python tools/asset_curation_entry_draft.py \
  --report <report.json> \
  --candidate <candidate_id_or_name> \
  --asset-id <final_asset_id> \
  --tag <tag> \
  --production-family ui-kit \
  --source-layout single \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<final_asset_id>.json
```

加上 `--request` 会切换到静态 `fx-bundle` 模式：把选中的图片绑定到它的原生 `Texture2D` 导入，写入 `compiled` entry，并记录 build fingerprint。之后带 `--result <result.json>` 再跑一次，会依据同一份 fingerprint 把 entry 提升为 `ready`。

## asset_finalize_entry_draft.py

`asset_finalize_entry_draft.py` 会把一次 `asset_image_finalize.py` 的报告转换成 v1 stable-entry draft。所有以单张 finalize 图片收尾的路径都用它：screen reference、背景与视差层，以及单张卡框或立绘框。它要求 finalize 运行成功、`--require-aspect` 在容差内、且带 `--label <asset_id>`；layout 由 family 推导——`screen-reference` 得到固定在 `references/` 的 `reference`，其余 family 得到固定在稳定输出目录的 `single`。

手动入口：

```bash
python tools/asset_finalize_entry_draft.py \
  --finalize-report <finalize_report.json> \
  --asset-id <asset_id> \
  --tag <tag> \
  --production-family screen-reference \
  --project-root . \
  --out .godotmaker/asset-generation/work/entries/<asset_id>.json
```

## asset_output_path.py

`asset_output_path.py` 是稳定输出目录 `assets/generated/<production_family>/<asset_id>/` 的唯一权威。一个素材所有可被 worker 消费的文件都放在这里，因此重新生成会就地覆盖，不会漂移到带时间戳或 `v2` 的路径。

手动入口：

```bash
python tools/asset_output_path.py --family <production_family> --asset-id <asset_id>
python tools/asset_output_path.py --entry <entry.json> --project-root . --check-files
```

## asset_atlas_assemble.py

`asset_atlas_assemble.py` 根据显式声明 slot rect 的 JSON 组装物理 PNG atlas。它不做 packing、trim、resize 或 region 推断。source 必须是相对 project root 的 PNG 路径，尺寸必须与声明的 slot 精确一致；输出 PNG 和 metadata 都必须位于 `assets/generated/<production_family>/<asset_id>/` 内。

手动入口：

```bash
python tools/asset_atlas_assemble.py \
  --declaration <fixed_slots.json> \
  --atlas-out assets/generated/ui-kit/<asset_id>/<asset_id>.png \
  --metadata-out assets/generated/ui-kit/<asset_id>/<asset_id>.json \
  --family ui-kit \
  --asset-id <asset_id> \
  --project-root .
```

该工具把物理 atlas 和确定性的 region metadata 作为可回滚的一对输出写入。它只负责固定 slot 的组装；把 metadata 编译成 `AtlasTexture` 是独立的 compiler 步骤。

## asset_stable_entry.py

`asset_stable_entry.py` 校验一个 v1 stable entry，并把它序列化到 `.godotmaker/asset-generation/entries/<tag>/<asset_id>.json`。entry 只保存稳定身份加上 `production_family`、`source_layout`、可选的最小 `godot_artifact` 和 `processing_status`，不保存其他字段。

对于非 `reference` entry，`godot_artifact.type` 必须是 Godot ClassDB
标识符，且必须位于下列封闭的 layout 兼容集合中；这不表示可以使用任意
ClassDB 类型：

| `source_layout.type` | 允许的 `godot_artifact.type` |
|---|---|
| `single` | `Texture2D` 或 `StyleBoxTexture` |
| `region_atlas` | `AtlasTexture` 或 `StyleBoxTexture` |
| `grid_sheet` | `SpriteFrames` |
| `theme_recipe` | `Theme` |
| `tile_atlas` | `TileSet` |
| `reference` | 不带 `godot_artifact` |

reference-only entry 只能使用 `pending`、`source_ready` 或 `failed`；其中只有
`source_ready` 是完成态，且它不是运行时 `ready`。

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
python tools/asset_generation_index.py --project-root . --check-entries --check-files
```

`--check-entries` 只做 schema 校验。`--check-files` 会额外检查每个 source 和 artifact 是否真的在磁盘上，并隐含 `--check-entries`，因此它才是完整的 handoff gate，能抓到注册之后被删除的素材。

把完整 entry 内容存在 `assets` 键下的旧 `runtime_artifact` manifest 会被拒绝并提示重新生成；不提供迁移或兼容读取。

## asset_assets_md_update.py

`asset_assets_md_update.py` 会根据已注册的 stable entry 更新 ASSETS.md 行。它先重新校验每个 entry 和被引用的文件。运行时行必须使用 `ready` 的非 reference entry，因此只有素材确实可被 worker 消费时才会变成 `generated`。`screen-reference` 行是例外：当 finalize 后的参考图文件、canonical stable entry 和 root-index 指针通过适用校验时，只能在 `source_ready` 变为 `generated`。它记录同一个 entry 指针，但绝不会创建 `godot_artifact` 或交给 worker 作为运行时资产。

手动入口：

```bash
python tools/asset_assets_md_update.py \
  --entry-file .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
```

## asset_runtime_resolver.py

`asset_runtime_resolver.py` 将一个已注册且状态为 `generated` 的 ASSETS.md 行解析为最小 runtime snapshot：`asset_id`、`production_family`、`source_layout` 和 `godot_artifact`。它要求 ASSETS.md 指针与 generated root index 一致，并校验 ready stable entry 及其引用文件；reference-only entry 不会产生 worker runtime snapshot。

手动入口：

```bash
python tools/asset_runtime_resolver.py --project-root . \
  --tag <tag> --asset-id <asset_id>
python tools/asset_runtime_resolver.py --project-root . \
  --manifest-entry .godotmaker/asset-generation/entries/<tag>/<asset_id>.json
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
9. 完成一张 finalize 后的场景参考图，而不把它当作运行时美术。

如果想更新 `/gm-evaluate` 用于对比的视觉目标，请重新运行 `/gm-asset`，不要直接编辑已生成的图片。
