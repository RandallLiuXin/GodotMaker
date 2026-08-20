# Wan 2.7 Image Provider

Use this file when `.godotmaker/config.yaml` sets `asset_image_model` to `wan`
or `wan:<model>`. The bare selector means `wan:wan2.7-image`; use
`wan:wan2.7-image-pro` explicitly for the higher-quality model. Do not use a
`wanxiang` alias.

## Source Generation

Write one spec per generated source under `.godotmaker/asset-generation/specs/`:

```json
{
  "asset_id": "<asset_id>",
  "model": "wan:wan2.7-image",
  "prompt": "<full prompt>",
  "prompt_path": ".godotmaker/asset-generation/prompts/<asset_id>.txt",
  "source_path": ".godotmaker/asset-generation/sources/<asset_id>_source.png",
  "size": "1K",
  "aspect_ratio": "16:9",
  "reference_inputs": [],
  "report_path": ".godotmaker/asset-generation/reports/<asset_id>_source.json"
}
```

Run:

```bash
python tools/asset_source_generate.py --spec <spec.json>
```

The tool calls Wan synchronously, downloads the short-lived returned URL in the
same execution, verifies it is PNG, and materializes the exact `source_path`.
The report records request ID, model, operation, usage, dimensions, and
role/path/hash provenance, but never an API key, Base64 image data, or result
URL.

## Requirements and regional routing

1. Set `DASHSCOPE_API_KEY`.
2. Set `DASHSCOPE_REGION` explicitly to `beijing` or `singapore`. API keys are
   regional; the tool never infers a region from a key.
3. Optionally set `DASHSCOPE_BASE_URL` to the matching public endpoint or a
   matching business-space endpoint. Use either the host or its `/api/v1`
   base (with or without a trailing slash); the full Wan generation endpoint
   is also accepted. Defaults are
   `https://dashscope.aliyuncs.com` for Beijing and
   `https://dashscope-intl.aliyuncs.com` for Singapore.
4. Run `python tools/check_env.py` after configuring the provider.

The preferred business-space forms are
`https://<workspace-id>.cn-beijing.maas.aliyuncs.com` and
`https://<workspace-id>.ap-southeast-1.maas.aliyuncs.com`. A region/base URL
mismatch fails before a network request.

## References and limits

Wan accepts 0–9 images. Put every required local image in `reference_inputs` as
`{ "role": "canonical|style|screen", "path": "<local image path>" }` in the
planned order. The generator sends each actual file as a Base64 data URI in that
same order, then the prompt. It validates up to 20 MB per image before Base64
encoding, a total encoded reference payload of at most 32 MB, 240–8000 px per
edge, a 1:8–8:1 ratio, and supported JPEG/JPG/PNG/BMP/WEBP formats.

Wan 2.7 does not accept transparent PNG inputs. This initial integration fails
closed only when actual alpha values are present; an RGBA PNG whose alpha is
fully opaque is accepted. Provide an opaque image rather than silently
flattening it. `wan2.7-image-pro` permits 4K only for text-to-image;
image editing is limited to 2K. The generator maps the shared `size` and
`aspect_ratio` deterministically to Wan's `WIDTH*HEIGHT` parameter; accepted
sizes are `1K`, `2K`, and `4K` (`512` is rejected), and it always
sends `watermark: false`.

## Handoff

After generation, keep the controlled source report with the processing and
finalization reports. Do not reuse a remote result URL as an asset, write
provenance by hand, substitute another provider, or retry through a different
provider.

## Explicit live smoke

Normal tests mock every Wan request. After configuring a non-production test
workspace and regional credentials, run the two text/reference paths twice each:

```bash
WAN_LIVE_SMOKE=1 python -m pytest tests/tools/test_wan_live_smoke.py -q
```

The fixed seed makes outputs comparatively stable but does not assert identical
pixels. Preserve the generated source and report for every successful request.
