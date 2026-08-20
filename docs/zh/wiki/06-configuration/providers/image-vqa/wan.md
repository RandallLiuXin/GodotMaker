# Wan 2.7 图片 provider

Wan 是供 `/gm-asset` 使用的阿里云百炼 API 图片 provider，不是 coding-agent runtime。

```yaml
asset_image_model: wan
# 或显式选择 Pro：
# asset_image_model: wan:wan2.7-image-pro
```

设置 `DASHSCOPE_API_KEY` 和 `DASHSCOPE_REGION`（`beijing` 或 `singapore`）。API Key 与 endpoint 按地域隔离，不能混用。`DASHSCOPE_BASE_URL` 可选；设置后必须使用对应地域的公共 DashScope endpoint 或业务空间专属域名，可以只写 host，也可以带 `/api/v1`（允许尾部斜杠）。运行 `python tools/check_env.py` 可检查配置。

Wan 支持文生图及按顺序传入 0–9 张参考图。流水线会传输真实 Base64 图片字节、在同一执行中下载并验证 PNG，并记录脱敏的请求与 usage 来源信息。因 Wan 2.7 不支持带 alpha 的 PNG 输入，透明参考图会被拒绝。
