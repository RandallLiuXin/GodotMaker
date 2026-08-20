# Wan 2.7 image provider

Wan is an Alibaba Cloud Model Studio API-backed image provider for `/gm-asset`.
It is not a coding-agent runtime.

```yaml
asset_image_model: wan
# Or select Pro explicitly:
# asset_image_model: wan:wan2.7-image-pro
```

Set `DASHSCOPE_API_KEY` and `DASHSCOPE_REGION` to `beijing` or `singapore`.
The key and endpoint are regional and cannot be mixed. `DASHSCOPE_BASE_URL` is
optional; if set, it must be the matching public DashScope endpoint or the
matching business-space endpoint. `python tools/check_env.py` checks this
configuration.

Wan supports text-to-image and 0–9 ordered references. The pipeline sends real
reference bytes as Base64, immediately downloads the returned PNG, and records
sanitized request/usage provenance. Transparent references are rejected because
Wan 2.7 does not accept PNG alpha inputs.
