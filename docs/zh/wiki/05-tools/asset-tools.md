# 资产工具

`ASSETS.md` 是 generated runtime asset 的唯一清单。Asset Skill 只产出已验证的通用 result，不创建单资源登记、索引或 worker handoff 文件。

## 登记完成的 result

`asset_result_registration.py` 会校验完整 request/result 生产单元，并原子写入 `ASSETS.md` 的全部声明逻辑输出。

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --request <request.json> --result <result.json> --godot-path <godot_path>
```

请求拥有输出集合：`scene-prop-set` 使用固定的 `spec.slots`；其他多输出 family 必须提供 `spec.outputs`。每个项目包含 `name`、`role`（`runtime` 或 `reference`），runtime 项还必须包含最终 `godot_type`。命令在写入前拒绝缺失、重复、额外、角色不符或类型不符的输出；runtime 文件必须在项目内、存在、能被 Godot 加载并匹配类型。

reference 输出会成为 `source_ready`，不会进入 worker handoff。

## Worker snapshot

直接从已生成的目录行派生最小 handoff：

```bash
python tools/asset_result_registration.py --assets-md ASSETS.md --tag <tag> \
  --snapshot --asset-id <logical_asset_id>
```

每个对象只包含 `asset_id` 与 `godot_artifact`（`type`、`path`）。不要手工编辑生成行或建立第二份索引。

## 生产辅助工具

素材生成、图片 finalize、sheet 处理、atlas 组装、curation 与 family validation 工具仍用于产生和验证真实文件；其证据留在 Skill report 中，登记始终使用上面的单一 result-to-`ASSETS.md` 命令。
