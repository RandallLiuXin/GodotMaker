#!/usr/bin/env python3
"""Generate API-backed asset source images from a JSON spec."""

import argparse
import base64
import hashlib
import io
import json
import math
import os
import sys
import tempfile
from contextlib import ExitStack
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from asset_image_finalize import ImageFinalizeError, finalize_image_asset


class SourceGenerateError(Exception):
    """Raised when source generation cannot complete."""


def result_json(ok: bool, cost_cents: int = 0, error: str | None = None, extra: dict | None = None):
    d = {"ok": ok, "cost_cents": cost_cents}
    if error:
        d["error"] = error
    if extra:
        d.update(extra)
    print(json.dumps(d))


def _validate_source(output: Path, asset_id: str) -> dict[str, object]:
    try:
        final = finalize_image_asset(
            output,
            output,
            image_format="png",
            label=asset_id,
        )
    except ImageFinalizeError as exc:
        raise SourceGenerateError(str(exc)) from exc
    return final


# --- Image backends ---

GEMINI_MODEL = "gemini-3.1-flash-image-preview"
GEMINI_SIZES = ["512", "1K", "2K", "4K"]
GEMINI_COSTS = {"512": 5, "1K": 7, "2K": 10, "4K": 15}
GEMINI_ASPECT_RATIOS = [
    "1:1", "1:4", "1:8", "2:3", "3:2", "3:4", "4:1", "4:3",
    "4:5", "5:4", "8:1", "9:16", "16:9", "21:9",
]

GROK_MODEL = "grok-imagine-image"  # 2 cents flat
GROK_COST = 2
GROK_SIZES = ["1K", "2K"]
GROK_ASPECT_RATIOS = [
    "1:1", "16:9", "9:16", "4:3", "3:4", "3:2", "2:3",
    "2:1", "1:2", "19.5:9", "9:19.5", "20:9", "9:20", "auto",
]

ALL_SIZES = ["512", "1K", "2K", "4K"]
ALL_ASPECT_RATIOS = sorted(set(GEMINI_ASPECT_RATIOS + GROK_ASPECT_RATIOS))
OPENAI_MODEL = "gpt-image-2"
OPENAI_MAX_REFERENCE_IMAGES = 16
OPENAI_COSTS = {"1:1": 5, "portrait": 7, "landscape": 7}
WAN_MODEL = "wan2.7-image"
WAN_PRO_MODEL = "wan2.7-image-pro"
WAN_MAX_REFERENCE_IMAGES = 9
WAN_TIMEOUT_SECONDS = 90
WAN_GENERATION_PATH = "/api/v1/services/aigc/multimodal-generation/generation"
WAN_API_BASE_PATH = "/api/v1"
WAN_MAX_REFERENCE_FILE_BYTES = 20 * 1024 * 1024
# The API's 20MB per-image limit applies before Base64 encoding. Keep the
# aggregate POST body bounded as well, because all references are inlined.
WAN_MAX_REFERENCE_PAYLOAD_BYTES = 32 * 1024 * 1024
WAN_MAX_DOWNLOAD_BYTES = 50 * 1024 * 1024
WAN_REGIONS = {
    "beijing": {
        "base_url": "https://dashscope.aliyuncs.com",
        "workspace_suffix": ".cn-beijing.maas.aliyuncs.com",
    },
    "singapore": {
        "base_url": "https://dashscope-intl.aliyuncs.com",
        "workspace_suffix": ".ap-southeast-1.maas.aliyuncs.com",
    },
}
WAN_SIZE_PIXELS = {"1K": 1024, "2K": 2048, "4K": 4096}
REFERENCE_ROLES = {"canonical", "style", "screen"}


def _split_model_selector(selector: str, *, default_provider: str,
                          default_model: str,
                          allow_bare_model: bool = False) -> tuple[str, str]:
    """Parse provider[:model] selectors while keeping provider-only aliases."""
    raw = (selector or "").strip()
    if not raw:
        return default_provider, default_model
    if ":" in raw:
        provider, model = raw.split(":", 1)
        provider = provider.strip()
        model = model.strip()
        if provider and model:
            return provider, model
    if raw in {"gemini", "openai", "grok", "wan", "native", "codex", "none"}:
        defaults = {
            "gemini": GEMINI_MODEL,
            "openai": OPENAI_MODEL,
            "grok": GROK_MODEL,
            "wan": WAN_MODEL,
            "native": "native",
            "codex": "codex",
            "none": "none",
        }
        return raw, defaults[raw]
    if allow_bare_model:
        return default_provider, raw
    return "", raw


def _mime_for_image(path: Path) -> str:
    """Detect image MIME type from decoded content, falling back to extension."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.load()
            detected_format = (image.format or "").upper()
    except Exception:
        detected_format = ""
    by_format = {
        "JPEG": "image/jpeg", "JPG": "image/jpeg",
        "PNG": "image/png", "WEBP": "image/webp", "BMP": "image/bmp",
    }
    if detected_format in by_format:
        return by_format[detected_format]
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
        ".bmp": "image/bmp",
    }.get(path.suffix.lower(), "image/png")


def _image_data_uri(image_path: Path) -> str:
    """Load image and return as base64 data URI."""
    b64 = base64.b64encode(image_path.read_bytes()).decode()
    mime = _mime_for_image(image_path)
    return f"data:{mime};base64,{b64}"


def _json_path(path: Path) -> str:
    return path.as_posix()


def _required_string(data: dict, field: str) -> str:
    value = data.get(field)
    if not isinstance(value, str) or not value.strip():
        raise SourceGenerateError(f"Spec field {field!r} must be a non-empty string")
    return value


def _optional_string(data: dict, field: str, default: str) -> str:
    value = data.get(field, default)
    if not isinstance(value, str) or not value.strip():
        raise SourceGenerateError(f"Spec field {field!r} must be a non-empty string")
    return value


def _readable_reference(path: Path) -> None:
    """Reject a missing or unreadable reference before any provider call."""
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.verify()
        with Image.open(path) as image:
            image.load()
    except Exception as exc:
        raise SourceGenerateError(f"Reference image is not readable: {path}") from exc


def _reference_inputs(data: dict) -> list[dict[str, object]]:
    """Read visible references while preserving their production role.

    ``reference_images`` is retained for existing production units. New callers
    should use ``reference_inputs`` so provider provenance can prove both the
    attached file and the role the prompt/production contract assigned to it.
    """
    if "reference_inputs" in data and "reference_images" in data:
        raise SourceGenerateError(
            "Spec must use either 'reference_inputs' or legacy 'reference_images', not both"
        )
    if "reference_inputs" in data:
        raw = data["reference_inputs"]
        if raw is None:
            return []
        if not isinstance(raw, list):
            raise SourceGenerateError("Spec field 'reference_inputs' must be a list")
        inputs: list[dict[str, object]] = []
        for index, item in enumerate(raw):
            if not isinstance(item, dict) or set(item) != {"role", "path"}:
                raise SourceGenerateError(
                    f"reference_inputs[{index}] must contain exactly role and path"
                )
            role, raw_path = item["role"], item["path"]
            if not isinstance(role, str) or role not in REFERENCE_ROLES:
                raise SourceGenerateError(
                    f"reference_inputs[{index}].role is not allowed: {role!r}"
                )
            if not isinstance(raw_path, str) or not raw_path.strip():
                raise SourceGenerateError(
                    f"reference_inputs[{index}].path must be a non-empty string"
                )
            path = Path(raw_path)
            if not path.is_file():
                raise SourceGenerateError(f"Reference image not found: {path}")
            _readable_reference(path)
            inputs.append({"role": role, "path": path})
        return inputs

    raw = data.get("reference_images", [])
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SourceGenerateError("Spec field 'reference_images' must be a list")
    inputs = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise SourceGenerateError(f"reference_images[{index}] must be a non-empty string")
        path = Path(item)
        if not path.is_file():
            raise SourceGenerateError(f"Reference image not found: {path}")
        _readable_reference(path)
        inputs.append({"role": None, "path": path})
    return inputs


def _reference_provenance(inputs: list[dict[str, object]]) -> list[dict[str, object]]:
    return [
        {
            "role": item["role"],
            "path": _json_path(item["path"]),
            "mime_type": _mime_for_image(item["path"]),
            "bytes": item["path"].stat().st_size,
            "sha256": hashlib.sha256(item["path"].read_bytes()).hexdigest(),
        }
        for item in inputs
    ]


def _generate_gemini(spec, output: Path, model_name: str):
    from google import genai
    from google.genai import types
    from PIL import Image

    config = types.GenerateContentConfig(
        response_modalities=["IMAGE"],
        image_config=types.ImageConfig(
            image_size=spec["size"],
            aspect_ratio=spec["aspect_ratio"],
        ),
    )

    contents = []
    for ref_path in spec["reference_images"]:
        contents.append(types.Part.from_bytes(data=ref_path.read_bytes(), mime_type=_mime_for_image(ref_path)))
    contents.append(spec["prompt"])

    client = genai.Client()
    response = client.models.generate_content(
        model=model_name,
        contents=contents,
        config=config,
    )

    if response.parts is None:
        reason = "unknown"
        if response.candidates and response.candidates[0].finish_reason:
            reason = response.candidates[0].finish_reason
        raise SourceGenerateError(f"Generation blocked (reason: {reason})")

    for part in response.parts:
        if part.inline_data is not None:
            img = Image.open(io.BytesIO(part.inline_data.data))
            img.save(output, format="PNG")
            return

    raise SourceGenerateError("No image returned")


def _generate_grok(spec, output: Path, model_name: str):
    import xai_sdk
    from PIL import Image

    image_url = None
    if spec["reference_images"]:
        image_url = _image_data_uri(spec["reference_images"][0])

    try:
        client = xai_sdk.Client()
        resp = client.image.sample(
            prompt=spec["prompt"],
            model=model_name,
            image_url=image_url,
            aspect_ratio=spec["aspect_ratio"],
            resolution=spec["size"].lower(),
        )
        img = Image.open(io.BytesIO(resp.image))
        img.save(output, format="PNG")
    except Exception as e:
        raise SourceGenerateError(str(e)) from e


def _openai_size(size: str, aspect_ratio: str) -> tuple[str, int]:
    if size != "1K":
        raise SourceGenerateError("OpenAI image generation supports size 1K only")
    if aspect_ratio == "1:1":
        return "1024x1024", OPENAI_COSTS["1:1"]
    try:
        left, right = aspect_ratio.split(":", 1)
        width_ratio = float(left)
        height_ratio = float(right)
    except ValueError as exc:
        raise SourceGenerateError(f"Invalid OpenAI aspect ratio: {aspect_ratio}") from exc
    if width_ratio <= 0 or height_ratio <= 0:
        raise SourceGenerateError(f"Invalid OpenAI aspect ratio: {aspect_ratio}")

    ratio = width_ratio / height_ratio
    if ratio > 3 or ratio < 1 / 3:
        raise SourceGenerateError("OpenAI aspect ratio must be between 1:3 and 3:1")

    def align16(value: float) -> int:
        return max(16, int(round(value / 16)) * 16)

    if ratio >= 1:
        width = 1536
        height = align16(width / ratio)
        return f"{width}x{height}", OPENAI_COSTS["landscape"]

    height = 1536
    width = align16(height * ratio)
    return f"{width}x{height}", OPENAI_COSTS["portrait"]


def _save_openai_b64(response, output: Path):
    from PIL import Image

    if not response.data or not response.data[0].b64_json:
        raise SourceGenerateError("No image returned")
    img = Image.open(io.BytesIO(base64.b64decode(response.data[0].b64_json)))
    img.save(output, format="PNG")


def _generate_openai(spec, output: Path, model_name: str):
    if len(spec["reference_images"]) > OPENAI_MAX_REFERENCE_IMAGES:
        raise SourceGenerateError(
            f"OpenAI image editing supports at most {OPENAI_MAX_REFERENCE_IMAGES} reference images"
        )

    from openai import OpenAI

    api_size, _ = _openai_size(spec["size"], spec["aspect_ratio"])
    client = OpenAI()
    try:
        if spec["reference_images"]:
            with ExitStack() as stack:
                image_files = [stack.enter_context(path.open("rb")) for path in spec["reference_images"]]
                image = image_files[0] if len(image_files) == 1 else image_files
                response = client.images.edit(
                    model=model_name,
                    image=image,
                    prompt=spec["prompt"],
                    size=api_size,
                )
        else:
            response = client.images.generate(
                model=model_name,
                prompt=spec["prompt"],
                size=api_size,
            )
    except Exception as e:
        raise SourceGenerateError(str(e)) from e

    _save_openai_b64(response, output)


def _wan_ratio(aspect_ratio: str) -> float:
    try:
        left, right = aspect_ratio.split(":", 1)
        width_ratio = float(left)
        height_ratio = float(right)
    except ValueError as exc:
        raise SourceGenerateError(f"Invalid Wan aspect ratio: {aspect_ratio}") from exc
    if width_ratio <= 0 or height_ratio <= 0:
        raise SourceGenerateError(f"Invalid Wan aspect ratio: {aspect_ratio}")
    ratio = width_ratio / height_ratio
    if not 1 / 8 <= ratio <= 8:
        raise SourceGenerateError("Wan aspect ratio must be between 1:8 and 8:1")
    return ratio


def _wan_size(size: str, aspect_ratio: str, model_name: str, has_references: bool) -> str:
    """Map the shared size/aspect contract to Wan's explicit WIDTH*HEIGHT form."""
    if size not in WAN_SIZE_PIXELS:
        raise SourceGenerateError("Wan supports size 1K, 2K, or 4K; size 512 is unsupported")
    if model_name not in {WAN_MODEL, WAN_PRO_MODEL}:
        raise SourceGenerateError(
            f"Unsupported Wan model {model_name!r}. Use {WAN_MODEL} or {WAN_PRO_MODEL}"
        )
    if size == "4K" and model_name != WAN_PRO_MODEL:
        raise SourceGenerateError("Wan 2.7 Image supports at most 2K; 4K requires wan2.7-image-pro")
    if size == "4K" and has_references:
        raise SourceGenerateError("Wan image editing supports at most 2K; use 1K or 2K references")

    ratio = _wan_ratio(aspect_ratio)
    target_side = WAN_SIZE_PIXELS[size]
    target_pixels = target_side * target_side
    height = round(math.sqrt(target_pixels / ratio))
    width = round(height * ratio)
    max_side = 4096 if not has_references and model_name == WAN_PRO_MODEL else 2048
    max_pixels = max_side * max_side
    # Rounding an explicit aspect can exceed the documented pixel cap by a few
    # pixels. Keep the closest bounded integer size instead of rejecting a
    # nominally valid 1K/2K request.
    if width * height > max_pixels:
        width = max_pixels // height
    if width * height < 768 * 768 or width * height > max_pixels:
        operation = "image editing" if has_references else "image generation"
        raise SourceGenerateError(
            f"Wan {operation} size {size} at {aspect_ratio} exceeds the model pixel limit; "
            "choose a smaller size or a less extreme aspect ratio"
        )
    return f"{width}*{height}"


def _validate_wan_reference(path: Path) -> int:
    """Fail closed for Wan's documented image-input limits, especially PNG alpha."""
    file_bytes = path.stat().st_size
    if file_bytes > WAN_MAX_REFERENCE_FILE_BYTES:
        raise SourceGenerateError(f"Wan reference exceeds 20MB: {path}")
    try:
        from PIL import Image

        with Image.open(path) as image:
            image.load()
            width, height = image.size
            ratio = width / height
            if "A" in image.getbands():
                alpha_min, _alpha_max = image.getchannel("A").getextrema()
                has_transparency = alpha_min < 255
            elif "transparency" in image.info:
                rgba = image.convert("RGBA")
                try:
                    alpha_min, _alpha_max = rgba.getchannel("A").getextrema()
                    has_transparency = alpha_min < 255
                finally:
                    rgba.close()
            else:
                has_transparency = False
            fmt = (image.format or path.suffix.lstrip(".")).upper()
    except Exception as exc:
        raise SourceGenerateError(f"Wan reference is not readable: {path}") from exc
    if fmt not in {"JPEG", "JPG", "PNG", "BMP", "WEBP"}:
        raise SourceGenerateError(f"Wan reference format is unsupported: {path}")
    if has_transparency:
        raise SourceGenerateError(
            "Wan 2.7 does not accept transparent reference images; provide an opaque reference instead: "
            f"{path}"
        )
    if not (240 <= width <= 8000 and 240 <= height <= 8000):
        raise SourceGenerateError(f"Wan reference dimensions must be 240..8000px: {path}")
    if not 1 / 8 <= ratio <= 8:
        raise SourceGenerateError(f"Wan reference aspect ratio must be between 1:8 and 8:1: {path}")
    return 4 * ((file_bytes + 2) // 3)


def _validated_https_url(value: str, error_message: str, *, allow_query: bool = False):
    """Parse an HTTPS URL without allowing malformed or nonstandard authority."""
    try:
        parsed = urlparse(value)
        port = parsed.port
    except ValueError as exc:
        raise SourceGenerateError(error_message) from exc
    hostname = parsed.hostname or ""
    if (
        parsed.scheme != "https"
        or not hostname
        or parsed.params
        or (parsed.query and not allow_query)
        or parsed.fragment
        or parsed.username
        or parsed.password
        or parsed.netloc.endswith(":")
        or port not in {None, 443}
    ):
        raise SourceGenerateError(error_message)
    return parsed, hostname


def wan_endpoint_from_config(region: str, base_url: str = "") -> str:
    """Validate a regional DashScope base URL and return the generation endpoint."""
    normalized_region = region.strip().lower()
    if normalized_region not in WAN_REGIONS:
        raise SourceGenerateError(
            "DASHSCOPE_REGION must be explicitly set to 'beijing' or 'singapore' for Wan"
        )
    candidate = base_url.strip() or WAN_REGIONS[normalized_region]["base_url"]
    parsed, hostname = _validated_https_url(
        candidate, "DASHSCOPE_BASE_URL must use the standard HTTPS authority"
    )
    public_host = urlparse(WAN_REGIONS[normalized_region]["base_url"]).hostname
    workspace_suffix = WAN_REGIONS[normalized_region]["workspace_suffix"]
    if hostname != public_host and not hostname.endswith(workspace_suffix):
        raise SourceGenerateError(
            f"DASHSCOPE_BASE_URL does not match DASHSCOPE_REGION={normalized_region}; "
            "use the region public endpoint or its business-space hostname"
        )
    path = parsed.path.rstrip("/")
    if path not in {"", WAN_API_BASE_PATH, WAN_GENERATION_PATH}:
        raise SourceGenerateError(
            "DASHSCOPE_BASE_URL may be the regional host, its /api/v1 base, "
            "or the Wan generation endpoint"
        )
    origin = f"{parsed.scheme}://{hostname}"
    return origin + (WAN_GENERATION_PATH if path != WAN_GENERATION_PATH else path)


def _wan_endpoint() -> tuple[str, str]:
    """Return a region-safe endpoint without guessing a key's home region."""
    region = os.environ.get("DASHSCOPE_REGION", "").strip().lower()
    configured = os.environ.get("DASHSCOPE_BASE_URL", "").strip()
    return wan_endpoint_from_config(region, configured), region


def _wan_error(prefix: str, *, status: int | None = None, body: str = "") -> SourceGenerateError:
    lowered = body.lower()
    code = ""
    try:
        parsed = json.loads(body)
        if isinstance(parsed, dict):
            code = str(parsed.get("code") or "")
            message = str(parsed.get("message") or "")
            lowered += " " + code.lower() + " " + message.lower()
    except ValueError:
        pass
    suffix = f" (HTTP {status})" if status is not None else ""
    if status in {401, 403}:
        return SourceGenerateError(
            "Wan authentication failed" + suffix + "; verify DASHSCOPE_API_KEY matches "
            "DASHSCOPE_REGION and DASHSCOPE_BASE_URL"
        )
    if status == 429:
        label = "quota exhausted" if "quota" in lowered else "rate limited"
        return SourceGenerateError(f"Wan request {label}{suffix}; retry later or check account quota")
    if status is not None and 500 <= status <= 599:
        return SourceGenerateError(f"Wan service error{suffix}; retry later")
    normalized_code = code.replace("_", "").replace("-", "").lower()
    if "datainspection" in normalized_code:
        return SourceGenerateError("Wan content moderation rejected the request" + suffix)
    if code:
        return SourceGenerateError(f"Wan API request failed ({code})" + suffix)
    return SourceGenerateError(prefix + suffix)


def _wan_request(endpoint: str, payload: dict[str, object], api_key: str) -> dict[str, object]:
    request = Request(
        endpoint,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=WAN_TIMEOUT_SECONDS) as response:
            raw = response.read()
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:4096]
        raise _wan_error("Wan API request failed", status=exc.code, body=body) from exc
    except TimeoutError as exc:
        raise SourceGenerateError("Wan API request timed out") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError) or "timed out" in str(exc.reason).lower():
            raise SourceGenerateError("Wan API request timed out") from exc
        raise SourceGenerateError("Wan API request could not reach DashScope") from exc
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise SourceGenerateError("Wan API returned invalid JSON") from exc
    if not isinstance(data, dict):
        raise SourceGenerateError("Wan API returned an invalid response object")
    if data.get("code") or data.get("message") and not data.get("output"):
        raise _wan_error("Wan API request failed", body=json.dumps(data, ensure_ascii=False))
    return data


def _download_wan_png(url: str, output: Path) -> None:
    _validated_https_url(url, "Wan returned an invalid image URL", allow_query=True)
    try:
        with urlopen(url, timeout=WAN_TIMEOUT_SECONDS) as response:
            raw = response.read(WAN_MAX_DOWNLOAD_BYTES + 1)
    except HTTPError as exc:
        raise SourceGenerateError(f"Wan result download failed (HTTP {exc.code})") from exc
    except TimeoutError as exc:
        raise SourceGenerateError("Wan result download timed out") from exc
    except URLError as exc:
        if isinstance(exc.reason, TimeoutError) or "timed out" in str(exc.reason).lower():
            raise SourceGenerateError("Wan result download timed out") from exc
        raise SourceGenerateError("Wan result download could not be reached") from exc
    if len(raw) > WAN_MAX_DOWNLOAD_BYTES:
        raise SourceGenerateError("Wan result download exceeded 50MB")
    try:
        from PIL import Image

        with Image.open(io.BytesIO(raw)) as image:
            image.load()
            if image.format != "PNG":
                raise SourceGenerateError("Wan result download was not a PNG image")
    except SourceGenerateError:
        raise
    except Exception as exc:
        raise SourceGenerateError("Wan result download was not a valid PNG image") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(delete=False, dir=output.parent, suffix=".png") as handle:
        temporary = Path(handle.name)
        handle.write(raw)
    try:
        temporary.replace(output)
    finally:
        if temporary.exists():
            temporary.unlink()


def _generate_wan(spec, output: Path, model_name: str) -> dict[str, object]:
    references = spec["reference_images"]
    if len(references) > WAN_MAX_REFERENCE_IMAGES:
        raise SourceGenerateError(
            f"Wan image editing supports at most {WAN_MAX_REFERENCE_IMAGES} reference images"
        )
    encoded_reference_bytes = sum(_validate_wan_reference(path) for path in references)
    if encoded_reference_bytes > WAN_MAX_REFERENCE_PAYLOAD_BYTES:
        raise SourceGenerateError(
            "Wan Base64 reference payload exceeds 32MB; use fewer or smaller reference images"
        )
    api_key = os.environ.get("DASHSCOPE_API_KEY", "").strip()
    if not api_key:
        raise SourceGenerateError("DASHSCOPE_API_KEY is not set for the selected Wan model")
    endpoint, region = _wan_endpoint()
    api_size = _wan_size(spec["size"], spec["aspect_ratio"], model_name, bool(references))
    content = [{"image": _image_data_uri(path)} for path in references]
    content.append({"text": spec["prompt"]})
    parameters: dict[str, object] = {"size": api_size, "n": 1, "watermark": False}
    if spec.get("seed") is not None:
        parameters["seed"] = spec["seed"]
    payload = {
        "model": model_name,
        "input": {"messages": [{"role": "user", "content": content}]},
        "parameters": parameters,
    }
    response = _wan_request(endpoint, payload, api_key)
    output_data = response.get("output")
    choices = output_data.get("choices") if isinstance(output_data, dict) else None
    if not isinstance(choices, list) or not choices:
        raise SourceGenerateError("Wan API returned no image choices")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise SourceGenerateError("Wan API returned an invalid image choice")
    message = first_choice.get("message")
    items = message.get("content") if isinstance(message, dict) else None
    image_url = next(
        (item.get("image") for item in items if isinstance(item, dict) and isinstance(item.get("image"), str)),
        None,
    ) if isinstance(items, list) else None
    if not image_url:
        raise SourceGenerateError("Wan API returned an image choice without a valid URL")
    _download_wan_png(image_url, output)
    usage = response.get("usage") if isinstance(response.get("usage"), dict) else {}
    return {
        "operation": "multimodal-generation.edit" if references else "multimodal-generation.generate",
        "reference_input_count": len(references),
        "references_attached": bool(references),
        "request_id": response.get("request_id"),
        "usage": usage,
        "requested_size": api_size,
        "region": region,
    }


def load_spec(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise SourceGenerateError(f"Invalid JSON spec: {path}") from exc
    if not isinstance(data, dict):
        raise SourceGenerateError("Spec must be a JSON object")

    prompt = _required_string(data, "prompt")
    prompt_path = Path(_required_string(data, "prompt_path"))
    source_path = Path(_required_string(data, "source_path"))
    asset_id = _required_string(data, "asset_id")
    selector = _required_string(data, "model")
    size = _optional_string(data, "size", "1K")
    aspect_ratio = _optional_string(data, "aspect_ratio", "1:1")
    seed = data.get("seed")
    if seed is not None and (type(seed) is not int or not 0 <= seed <= 2_147_483_647):
        raise SourceGenerateError("Spec field 'seed' must be an integer between 0 and 2147483647")
    reference_inputs = _reference_inputs(data)
    reference_images = [item["path"] for item in reference_inputs]
    report_path = data.get("report_path")
    if report_path is not None and (not isinstance(report_path, str) or not report_path.strip()):
        raise SourceGenerateError("Spec field 'report_path' must be a non-empty string")

    return {
        "asset_id": asset_id,
        "model": selector,
        "prompt": prompt,
        "prompt_path": prompt_path,
        "source_path": source_path,
        "size": size,
        "aspect_ratio": aspect_ratio,
        "seed": seed,
        "reference_images": reference_images,
        "reference_inputs": reference_inputs,
        "report_path": Path(report_path) if report_path else None,
    }


def generate_source(spec: dict) -> dict[str, object]:
    selector = spec["model"]
    backend, model_name = _split_model_selector(
        selector,
        default_provider="gemini",
        default_model=GEMINI_MODEL,
    )
    if backend in {"native", "codex"}:
        raise SourceGenerateError(f"Model selector {backend!r} is runtime-native")
    if backend not in {"gemini", "openai", "grok", "wan"}:
        raise SourceGenerateError(
            f"Invalid API-backed image model selector: {selector!r}"
        )
    size = spec["size"]

    if backend == "gemini":
        if size not in GEMINI_SIZES:
            raise SourceGenerateError(f"Gemini does not support size {size}. Use: {', '.join(GEMINI_SIZES)}")
        cost = GEMINI_COSTS[size]
    elif backend == "grok":
        if size not in GROK_SIZES:
            raise SourceGenerateError(f"Grok does not support size {size}. Use: {', '.join(GROK_SIZES)}")
        cost = GROK_COST
    elif backend == "wan":
        # Wan pricing changes by region/model; retain provider usage instead of
        # fabricating a local cents estimate.
        _wan_size(size, spec["aspect_ratio"], model_name, bool(spec["reference_images"]))
        cost = 0
    else:
        _, cost = _openai_size(size, spec["aspect_ratio"])

    output = Path(spec["source_path"])
    output.parent.mkdir(parents=True, exist_ok=True)
    spec["prompt_path"].parent.mkdir(parents=True, exist_ok=True)
    spec["prompt_path"].write_text(spec["prompt"], encoding="utf-8")

    label = f"{backend} {size} {spec['aspect_ratio']}"
    if spec["reference_images"]:
        label += " (image-to-image)"
    print(f"Generating source image ({label})...", file=sys.stderr)

    wan_payload: dict[str, object] | None = None
    if backend == "gemini":
        _generate_gemini(spec, output, model_name)
    elif backend == "grok":
        _generate_grok(spec, output, model_name)
    elif backend == "wan":
        wan_payload = _generate_wan(spec, output, model_name)
    else:
        _generate_openai(spec, output, model_name)

    final = _validate_source(output, spec["asset_id"])
    result = {
        "ok": True,
        "asset_id": spec["asset_id"],
        "provider": backend,
        "model": model_name,
        "source_path": _json_path(output),
        "prompt_path": _json_path(spec["prompt_path"]),
        "reference_images": [_json_path(path) for path in spec["reference_images"]],
        "reference_inputs": _reference_provenance(spec["reference_inputs"]),
        "provider_payload": wan_payload or {
            "operation": (
                "images.edit" if backend == "openai" and spec["reference_images"]
                else "images.generate" if backend == "openai"
                else "models.generate_content"
            ),
            "reference_input_count": len(spec["reference_images"]),
            "references_attached": bool(spec["reference_images"]),
        },
        "cost_cents": cost,
        "bytes": final["bytes"],
        "width": final["width"],
        "height": final["height"],
        "format": final["format"],
        "mode": final["mode"],
        "original_width": final["original_width"],
        "original_height": final["original_height"],
    }
    if spec["report_path"] is not None:
        result["report_path"] = _json_path(spec["report_path"])
        spec["report_path"].parent.mkdir(parents=True, exist_ok=True)
        spec["report_path"].write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    return result


def main():
    parser = argparse.ArgumentParser(description="Generate API-backed asset source images")
    parser.add_argument("--spec", required=True, help="JSON source-generation spec path")
    args = parser.parse_args()
    try:
        spec = load_spec(Path(args.spec))
        result = generate_source(spec)
    except SourceGenerateError as exc:
        result_json(False, error=str(exc))
        return 1
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main())
