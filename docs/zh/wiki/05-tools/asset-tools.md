# 资产工具

GodotMaker 使用一组 Python 工具生成、处理和验证 2D 资产。`/gm-asset`
负责协调完整流程；单独运行工具主要用于诊断某个输入、处理步骤或资源结果。

`ASSETS.md` 是 generated runtime asset 的唯一清单。Asset Skill 产生通过验证的通用
result；登记器直接消费该 result，不再创建单资源登记、索引或额外的 worker handoff
文件。

## 登记已验证的 result

`asset_result_registration.py` 校验完整 request/result 生产单元，并原子更新
`ASSETS.md` 中全部声明的逻辑输出。

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --request <request.json> --result <result.json> --godot-path <godot_path>
```

request 决定 runtime 输出集合。`scene-prop-set` 和 `compact-prop-pack` 使用
固定的 `spec.slots`；`platform-strip` 使用 `spec.segments` 和选定的
`spec.kind`；`ui-kit` 与 `card-kit` 使用其 `styleboxes`、`atlas_regions` 和可选的
`theme`。其他 runtime family 从 request 推导唯一 runtime 输出，不接受并行的
`spec.outputs` 声明。写入前会拒绝缺少、重复、额外、角色不匹配或类型不匹配的
runtime 输出。runtime 文件还必须位于项目内、确实存在、能被 Godot 加载，且实际
类型匹配声明。

runtime family 返回的 reference 输出是已验证的源证据，不是目录行。只有
`screen-reference` 等 reference-only family 会登记 `source_ready` 行；其路径为
项目相对路径（例如 `references/title_screen.png`），不会进入 worker runtime handoff。

## 读取 worker snapshot

从已生成的目录行直接派生最小 handoff：

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --snapshot --asset-id <logical_asset_id>
```

每个对象只包含 `asset_id` 和 `godot_artifact`（`type`、`path`）。不要手动编辑
已生成行，也不要手工建立第二份索引。

## 生产辅助工具

以下工具仍是实际生产流程的一部分；它们生成或验证源文件及原生 Godot 资源，证据
保存在 Skill report 中，最终登记始终通过上一节的 result-to-`ASSETS.md` 命令完成。

| 工具 | 用途 |
|---|---|
| `asset_source_generate.py` | 按 JSON spec 调用图像提供方，生成带来源记录的 source 图片。 |
| `asset_layout_guide.py` | 为固定网格 source 图片生成 slot、标签和安全边距参考图。 |
| `asset_image_finalize.py` | 完成单张图片的透明度、边界、比例和最终文件检查。 |
| `asset_sheet_process.py` | 对 UI、图标和道具 sheet 做透明化、切分、候选提取与报告。 |
| `asset_action_process.py` | 处理角色或动画特效的动作 sheet，输出帧、透明 sheet 和动画报告。 |
| `asset_curation_select.py` | 从 curation 报告中选择候选资源并写入最终资产路径。 |
| `asset_atlas_assemble.py` | 依据显式 slot rect 组装固定布局的 PNG atlas 和 region metadata。 |
| `asset_ui_source_sheet_plan.py` / `asset_ui_stylebox_plan.py` | 为 UI 组件 sheet 及 StyleBoxTexture 编译生成确定性计划。 |
| `asset_tileset_profile.py` | 生成 TileSet profile、atlas 指引和原生 TileSet 编译配方。 |
| `asset_family_registry.py` | 输出或校验公开 Asset Skill family、variant、输出类型与基数合同。 |

常用的结构检查命令：

```bash
python tools/asset_family_registry.py --check
```

大多数情况下无需手动串联这些工具。应通过 `/gm-asset` 让它按照 `ASSETS.md`、
request 和 Skill 合同调度；手动执行适用于定位单个 source、测试固定网格、排查
切分结果，或复现资源登记失败。
