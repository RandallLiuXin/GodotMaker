#!/usr/bin/env python3
"""Generate API-backed asset source images from a JSON spec."""

import argparse
import base64
import io
import json
import sys
from contextlib import ExitStack
from pathlib import Path

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
    if raw in {"gemini", "openai", "grok", "native", "codex", "none"}:
        defaults = {
            "gemini": GEMINI_MODEL,
            "openai": OPENAI_MODEL,
            "grok": GROK_MODEL,
            "native": "native",
            "codex": "codex",
            "none": "none",
        }
        return raw, defaults[raw]
    if allow_bare_model:
        return default_provider, raw
    return "", raw


def _mime_for_image(path: Path) -> str:
    """Detect image MIME type from file extension."""
    return {
        ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".png": "image/png", ".webp": "image/webp",
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


def _reference_images(data: dict) -> list[Path]:
    raw = data.get("reference_images", [])
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise SourceGenerateError("Spec field 'reference_images' must be a list")
    paths: list[Path] = []
    for index, item in enumerate(raw):
        if not isinstance(item, str) or not item.strip():
            raise SourceGenerateError(f"reference_images[{index}] must be a non-empty string")
        path = Path(item)
        if not path.exists():
            raise SourceGenerateError(f"Reference image not found: {path}")
        paths.append(path)
    return paths


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
    reference_images = _reference_images(data)
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
        "reference_images": reference_images,
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
    if backend not in {"gemini", "openai", "grok"}:
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

    if backend == "gemini":
        _generate_gemini(spec, output, model_name)
    elif backend == "grok":
        _generate_grok(spec, output, model_name)
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
