import io
import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

import asset_source_generate as source_generate  # noqa: E402


def make_spec(tmp_path: Path, **overrides):
    spec = {
        "asset_id": "coin",
        "model": "grok",
        "prompt": "a gold coin icon on a solid green background",
        "prompt_path": ".godotmaker/asset-generation/prompts/coin.txt",
        "source_path": ".godotmaker/asset-generation/sources/coin_source.png",
        "size": "1K",
        "aspect_ratio": "1:1",
    }
    for key, value in overrides.items():
        if value is None:
            spec.pop(key, None)
        else:
            spec[key] = value
    path = tmp_path / "spec.json"
    path.write_text(json.dumps(spec), encoding="utf-8")
    return path


def write_png(path: Path, size=(12, 10)):
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", size, (255, 210, 40)).save(path, format="PNG")


def png_bytes(size=(12, 10)):
    buf = source_generate.io.BytesIO()
    Image.new("RGB", size, (255, 210, 40)).save(buf, format="PNG")
    return buf.getvalue()


def write_refs(tmp_path: Path, count: int, size=(12, 10)) -> list[str]:
    refs = []
    for index in range(count):
        path = tmp_path / f"ref-{index}.png"
        write_png(path, size=size)
        refs.append(str(path))
    return refs


def write_reference_inputs(tmp_path: Path, count: int) -> list[dict[str, str]]:
    roles = ("canonical", "style", "screen")
    return [
        {"role": roles[index % len(roles)], "path": path}
        for index, path in enumerate(write_refs(tmp_path, count))
    ]


def test_load_spec_requires_explicit_model(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec_path = make_spec(tmp_path, model="")

    with pytest.raises(source_generate.SourceGenerateError, match="model"):
        source_generate.load_spec(spec_path)


def test_load_spec_allows_an_empty_optional_reference_list(tmp_path):
    spec = source_generate.load_spec(make_spec(tmp_path, reference_images=None))

    assert spec["reference_images"] == []
    assert spec["reference_inputs"] == []


def test_generate_source_writes_prompt_source_and_report(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(
        make_spec(
            tmp_path,
            report_path=".godotmaker/asset-generation/reports/coin_source.json",
        )
    )

    def fake_grok(spec_data, output, _model_name):
        assert spec_data["prompt"] == "a gold coin icon on a solid green background"
        write_png(output)

    monkeypatch.setattr(source_generate, "_generate_grok", fake_grok)

    result = source_generate.generate_source(spec)

    assert result["ok"] is True
    assert result["provider"] == "grok"
    assert result["asset_id"] == "coin"
    assert result["source_path"] == ".godotmaker/asset-generation/sources/coin_source.png"
    assert result["prompt_path"] == ".godotmaker/asset-generation/prompts/coin.txt"
    assert result["report_path"] == ".godotmaker/asset-generation/reports/coin_source.json"
    assert (tmp_path / result["source_path"]).exists()
    assert (tmp_path / result["prompt_path"]).read_text(encoding="utf-8") == spec["prompt"]

    report = json.loads((tmp_path / result["report_path"]).read_text(encoding="utf-8"))
    assert report["source_path"] == result["source_path"]


def test_generate_source_supports_openai_selector(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(
        make_spec(
            tmp_path,
            model="openai:gpt-image-2",
            report_path=".godotmaker/asset-generation/reports/coin_source.json",
        )
    )

    def fake_openai(spec_data, output, model_name):
        assert model_name == "gpt-image-2"
        assert spec_data["aspect_ratio"] == "1:1"
        write_png(output)

    monkeypatch.setattr(source_generate, "_generate_openai", fake_openai)

    result = source_generate.generate_source(spec)

    assert result["ok"] is True
    assert result["provider"] == "openai"
    assert result["model"] == "gpt-image-2"
    assert result["cost_cents"] == 5
    assert (tmp_path / result["source_path"]).exists()
    assert (tmp_path / result["report_path"]).exists()


class FakeHTTPResponse:
    def __init__(self, body: bytes):
        self.body = body

    def read(self, *_args):
        return self.body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False


def wan_success_response(url="https://result.example/image.png"):
    return {
        "request_id": "wan-request-123",
        "usage": {"image_count": 1, "size": "1365*768"},
        "output": {
            "choices": [{"message": {"content": [{"type": "image", "image": url}]}}]
        },
    }


def test_wan_selector_defaults_to_wan_27_image(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(make_spec(tmp_path, model="wan"))
    monkeypatch.setattr(source_generate, "_generate_wan", lambda *_args: write_png(_args[1]) or {})

    result = source_generate.generate_source(spec)

    assert result["provider"] == "wan"
    assert result["model"] == "wan2.7-image"


def test_wan_posts_ordered_reference_bytes_and_downloads_png(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    refs = write_refs(tmp_path, 9, size=(240, 240))
    spec = source_generate.load_spec(
        make_spec(
            tmp_path,
            model="wan:wan2.7-image-pro",
            size="2K",
            aspect_ratio="16:9",
            reference_inputs=[{"role": "style", "path": path} for path in refs],
            report_path=".godotmaker/asset-generation/reports/coin_source.json",
        )
    )
    seen = []
    response_body = json.dumps(wan_success_response()).encode()

    def fake_urlopen(request, timeout):
        seen.append((request, timeout))
        if isinstance(request, str):
            return FakeHTTPResponse(png_bytes((64, 48)))
        return FakeHTTPResponse(response_body)

    monkeypatch.setattr(source_generate, "urlopen", fake_urlopen)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "not-a-real-key")
    monkeypatch.setenv("DASHSCOPE_REGION", "beijing")

    result = source_generate.generate_source(spec)

    request = seen[0][0]
    payload = json.loads(request.data.decode())
    content = payload["input"]["messages"][0]["content"]
    assert request.full_url.startswith("https://dashscope.aliyuncs.com/")
    assert request.get_header("Authorization") == "Bearer not-a-real-key"
    assert payload["model"] == "wan2.7-image-pro"
    assert payload["parameters"] == {"size": "2730*1536", "n": 1, "watermark": False}
    assert [entry["image"].split(",", 1)[1] for entry in content[:-1]] == [
        source_generate.base64.b64encode(Path(path).read_bytes()).decode() for path in refs
    ]
    assert content[-1] == {"text": spec["prompt"]}
    assert Path(result["source_path"]).is_file()
    assert result["provider_payload"]["request_id"] == "wan-request-123"
    assert result["provider_payload"]["usage"] == {"image_count": 1, "size": "1365*768"}
    report = Path(result["report_path"]).read_text(encoding="utf-8")
    assert "not-a-real-key" not in report
    assert "data:image" not in report
    assert "result.example" not in report


def test_wan_text_generation_uses_singapore_business_space_endpoint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(make_spec(tmp_path, model="wan", aspect_ratio="9:16"))
    calls = []

    def fake_urlopen(request, timeout):
        calls.append(request)
        if isinstance(request, str):
            return FakeHTTPResponse(png_bytes())
        return FakeHTTPResponse(json.dumps(wan_success_response()).encode())

    monkeypatch.setattr(source_generate, "urlopen", fake_urlopen)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    monkeypatch.setenv("DASHSCOPE_REGION", "singapore")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "https://space.ap-southeast-1.maas.aliyuncs.com")

    source_generate.generate_source(spec)

    payload = json.loads(calls[0].data.decode())
    assert calls[0].full_url.startswith("https://space.ap-southeast-1.maas.aliyuncs.com/")
    assert payload["parameters"]["size"] == "768*1365"


@pytest.mark.parametrize(
    "base_url",
    [
        "https://dashscope.aliyuncs.com/api/v1",
        "https://dashscope.aliyuncs.com/api/v1/",
        "https://ws-abc.cn-beijing.maas.aliyuncs.com/api/v1/",
        "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation",
    ],
)
def test_wan_endpoint_accepts_official_base_url_forms(base_url):
    assert source_generate.wan_endpoint_from_config("beijing", base_url) == (
        "https://" + base_url.split("//", 1)[1].split("/", 1)[0]
        + "/api/v1/services/aigc/multimodal-generation/generation"
    )


@pytest.mark.parametrize(
    "base_url",
    [
        "https://dashscope.aliyuncs.com:abc",
        "https://dashscope.aliyuncs.com:8443",
        "https://dashscope.aliyuncs.com:",
        "https://user@dashscope.aliyuncs.com",
    ],
)
def test_wan_endpoint_rejects_invalid_authorities(base_url):
    with pytest.raises(source_generate.SourceGenerateError, match="HTTPS"):
        source_generate.wan_endpoint_from_config("beijing", base_url)


def test_wan_endpoint_rejects_unparseable_authority():
    with pytest.raises(source_generate.SourceGenerateError, match="HTTPS"):
        source_generate.wan_endpoint_from_config("beijing", "https://[broken")


def test_wan_endpoint_normalizes_explicit_default_port():
    assert source_generate.wan_endpoint_from_config(
        "beijing", "https://dashscope.aliyuncs.com:443"
    ) == "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"


def test_wan_allows_fully_opaque_rgba_reference_and_reports_bmp_mime(tmp_path):
    rgba = tmp_path / "opaque-rgba.png"
    Image.new("RGBA", (240, 240), (1, 2, 3, 255)).save(rgba)
    assert source_generate._validate_wan_reference(rgba) > 0

    bmp = tmp_path / "reference.bmp"
    Image.new("RGB", (240, 240), (1, 2, 3)).save(bmp)
    assert source_generate._image_data_uri(bmp).startswith("data:image/bmp;base64,")
    assert source_generate._reference_provenance([{"role": "style", "path": bmp}])[0]["mime_type"] == "image/bmp"

    disguised_bmp = tmp_path / "reference.png"
    Image.new("RGB", (240, 240), (1, 2, 3)).save(disguised_bmp, format="BMP")
    assert source_generate._validate_wan_reference(disguised_bmp) > 0
    assert source_generate._image_data_uri(disguised_bmp).startswith("data:image/bmp;base64,")
    assert source_generate._reference_provenance(
        [{"role": "style", "path": disguised_bmp}]
    )[0]["mime_type"] == "image/bmp"


def test_wan_rejects_unsupported_512_and_oversized_reference_payload(tmp_path, monkeypatch):
    with pytest.raises(source_generate.SourceGenerateError, match="512 is unsupported"):
        source_generate._wan_size("512", "1:1", "wan2.7-image", False)

    refs = write_refs(tmp_path, 2, size=(240, 240))
    spec = source_generate.load_spec(make_spec(tmp_path, model="wan", reference_images=refs))
    monkeypatch.setattr(source_generate, "WAN_MAX_REFERENCE_PAYLOAD_BYTES", 1)
    with pytest.raises(source_generate.SourceGenerateError, match="payload exceeds"):
        source_generate._generate_wan(spec, Path(spec["source_path"]), "wan2.7-image")


def test_wan_keeps_invalid_parameter_distinct_from_content_moderation():
    error = source_generate._wan_error(
        "Wan API request failed",
        body=json.dumps({
            "code": "InvalidParameter",
            "message": "input.messages[0].content[0].image is invalid",
        }),
    )

    assert "InvalidParameter" in str(error)
    assert "moderation" not in str(error)


def test_wan_download_rejects_non_png_http_error_and_oversized_body(tmp_path, monkeypatch):
    output = tmp_path / "output.png"
    monkeypatch.setattr(source_generate, "urlopen", lambda *_args, **_kwargs: FakeHTTPResponse(b"not a png"))
    with pytest.raises(source_generate.SourceGenerateError, match="valid PNG"):
        source_generate._download_wan_png("https://result.example/image.png", output)

    def http_error(request, timeout):
        raise source_generate.HTTPError(str(request), 502, "bad gateway", {}, io.BytesIO())

    monkeypatch.setattr(source_generate, "urlopen", http_error)
    with pytest.raises(source_generate.SourceGenerateError, match=r"download failed \(HTTP 502\)"):
        source_generate._download_wan_png("https://result.example/image.png", output)

    monkeypatch.setattr(source_generate, "WAN_MAX_DOWNLOAD_BYTES", 10)
    monkeypatch.setattr(source_generate, "urlopen", lambda *_args, **_kwargs: FakeHTTPResponse(b"x" * 11))
    with pytest.raises(source_generate.SourceGenerateError, match="exceeded"):
        source_generate._download_wan_png("https://result.example/image.png", output)


def test_wan_download_requires_https(tmp_path):
    with pytest.raises(source_generate.SourceGenerateError, match="invalid image URL"):
        source_generate._download_wan_png("http://result.example/image.png", tmp_path / "output.png")

    with pytest.raises(source_generate.SourceGenerateError, match="invalid image URL"):
        source_generate._download_wan_png("https://result.example:abc/image.png", tmp_path / "output.png")

    with pytest.raises(source_generate.SourceGenerateError, match="invalid image URL"):
        source_generate._download_wan_png("https://[broken", tmp_path / "output.png")


def test_wan_download_allows_signed_https_query(tmp_path, monkeypatch):
    signed_url = "https://result.example/image.png?Expires=123&Signature=signed-value"
    seen = []

    def fake_urlopen(url, timeout):
        seen.append((url, timeout))
        return FakeHTTPResponse(png_bytes())

    monkeypatch.setattr(source_generate, "urlopen", fake_urlopen)
    output = tmp_path / "output.png"
    source_generate._download_wan_png(signed_url, output)

    assert seen == [(signed_url, source_generate.WAN_TIMEOUT_SECONDS)]
    assert output.is_file()


def test_wan_rejects_missing_key_and_region_base_mismatch(tmp_path, monkeypatch):
    spec = source_generate.load_spec(make_spec(tmp_path, model="wan"))
    monkeypatch.delenv("DASHSCOPE_API_KEY", raising=False)
    monkeypatch.setenv("DASHSCOPE_REGION", "beijing")
    with pytest.raises(source_generate.SourceGenerateError, match="DASHSCOPE_API_KEY"):
        source_generate._generate_wan(spec, Path(spec["source_path"]), "wan2.7-image")

    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    monkeypatch.setenv("DASHSCOPE_BASE_URL", "https://dashscope-intl.aliyuncs.com")
    with pytest.raises(source_generate.SourceGenerateError, match="does not match"):
        source_generate._generate_wan(spec, Path(spec["source_path"]), "wan2.7-image")


@pytest.mark.parametrize(
    ("status", "body", "message"),
    [
        (401, b'{"code":"InvalidApiKey"}', "authentication"),
        (429, b'{"code":"QuotaExhausted"}', "quota exhausted"),
        (500, b'{"code":"InternalError"}', "service error"),
        (400, b'{"code":"DataInspectionFailed"}', "content moderation"),
    ],
)
def test_wan_classifies_http_errors(tmp_path, monkeypatch, status, body, message):
    spec = source_generate.load_spec(make_spec(tmp_path, model="wan"))

    def fake_urlopen(request, timeout):
        raise source_generate.HTTPError(request.full_url, status, "failed", {}, io.BytesIO(body))

    monkeypatch.setattr(source_generate, "urlopen", fake_urlopen)
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    monkeypatch.setenv("DASHSCOPE_REGION", "beijing")

    with pytest.raises(source_generate.SourceGenerateError, match=message):
        source_generate._generate_wan(spec, Path(spec["source_path"]), "wan2.7-image")


def test_wan_classifies_timeout_empty_choices_and_bad_download_url(tmp_path, monkeypatch):
    spec = source_generate.load_spec(make_spec(tmp_path, model="wan"))
    monkeypatch.setenv("DASHSCOPE_API_KEY", "test")
    monkeypatch.setenv("DASHSCOPE_REGION", "beijing")
    monkeypatch.setattr(source_generate, "urlopen", lambda *_args, **_kwargs: (_ for _ in ()).throw(TimeoutError()))
    with pytest.raises(source_generate.SourceGenerateError, match="timed out"):
        source_generate._generate_wan(spec, Path(spec["source_path"]), "wan2.7-image")

    monkeypatch.setattr(source_generate, "_wan_request", lambda *_args: {"output": {"choices": []}})
    with pytest.raises(source_generate.SourceGenerateError, match="no image choices"):
        source_generate._generate_wan(spec, Path(spec["source_path"]), "wan2.7-image")

    monkeypatch.setattr(source_generate, "_wan_request", lambda *_args: wan_success_response("not-a-url"))
    with pytest.raises(source_generate.SourceGenerateError, match="invalid image URL"):
        source_generate._generate_wan(spec, Path(spec["source_path"]), "wan2.7-image")


def test_wan_rejects_more_than_nine_or_transparent_references(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(make_spec(tmp_path, model="wan", reference_images=write_refs(tmp_path, 10, size=(240, 240))))
    with pytest.raises(source_generate.SourceGenerateError, match="at most 9"):
        source_generate._generate_wan(spec, Path(spec["source_path"]), "wan2.7-image")

    alpha = tmp_path / "alpha.png"
    Image.new("RGBA", (240, 240), (1, 2, 3, 0)).save(alpha)
    spec = source_generate.load_spec(make_spec(tmp_path, model="wan", reference_images=[str(alpha)]))
    with pytest.raises(source_generate.SourceGenerateError, match="transparent"):
        source_generate._generate_wan(spec, Path(spec["source_path"]), "wan2.7-image")


def test_openai_uses_all_reference_images_for_edit(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(
        make_spec(
            tmp_path,
            model="openai:gpt-image-2",
            reference_images=write_refs(tmp_path, 2),
        )
    )
    seen = {}
    image_b64 = source_generate.base64.b64encode(png_bytes()).decode()
    output = Path(spec["source_path"])
    output.parent.mkdir(parents=True, exist_ok=True)

    class FakeImages:
        def edit(self, **kwargs):
            seen.update(kwargs)
            assert all(not image.closed for image in kwargs["image"])
            assert [Path(image.name).name for image in kwargs["image"]] == [
                "ref-0.png",
                "ref-1.png",
            ]
            return SimpleNamespace(data=[SimpleNamespace(b64_json=image_b64)])

        def generate(self, **_kwargs):
            raise AssertionError("reference image specs must use images.edit")

    class FakeOpenAI:
        def __init__(self):
            self.images = FakeImages()

    monkeypatch.setitem(
        sys.modules,
        "openai",
        SimpleNamespace(OpenAI=FakeOpenAI),
    )

    source_generate._generate_openai(spec, output, "gpt-image-2")

    assert seen["model"] == "gpt-image-2"
    assert seen["prompt"] == spec["prompt"]
    assert seen["size"] == "1024x1024"
    assert (tmp_path / spec["source_path"]).exists()


def test_role_preserving_reference_inputs_are_attached_and_reported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    refs = write_refs(tmp_path, 2)
    inputs = [
        {"role": "style", "path": refs[0]},
        {"role": "screen", "path": refs[1]},
    ]
    spec = source_generate.load_spec(
        make_spec(
            tmp_path,
            model="openai:gpt-image-2",
            reference_inputs=inputs,
            report_path=".godotmaker/asset-generation/reports/coin_source.json",
        )
    )

    def fake_openai(spec_data, output, model_name):
        assert model_name == "gpt-image-2"
        assert [str(path) for path in spec_data["reference_images"]] == [
            item["path"] for item in inputs
        ]
        write_png(output)

    monkeypatch.setattr(source_generate, "_generate_openai", fake_openai)
    result = source_generate.generate_source(spec)

    assert [item["role"] for item in result["reference_inputs"]] == [
        "style", "screen"
    ]
    assert result["provider_payload"] == {
        "operation": "images.edit",
        "reference_input_count": 2,
        "references_attached": True,
    }
    assert all(len(item["sha256"]) == 64 for item in result["reference_inputs"])
    report = json.loads((tmp_path / result["report_path"]).read_text(encoding="utf-8"))
    assert report["reference_inputs"] == result["reference_inputs"]


@pytest.mark.parametrize(
    ("reference_inputs", "error"),
    [
        ([{"role": "palette", "path": "reference.png"}], "not allowed"),
        ([{"role": "style", "path": "missing.png"}], "not found"),
    ],
)
def test_load_spec_rejects_invalid_role_preserved_references(tmp_path, reference_inputs, error):
    with pytest.raises(source_generate.SourceGenerateError, match=error):
        source_generate.load_spec(make_spec(tmp_path, reference_inputs=reference_inputs))


def test_load_spec_rejects_ambiguous_reference_input_forms(tmp_path):
    reference = tmp_path / "reference.png"
    write_png(reference)

    with pytest.raises(source_generate.SourceGenerateError, match="either"):
        source_generate.load_spec(
            make_spec(
                tmp_path,
                reference_images=[str(reference)],
                reference_inputs=[{"role": "style", "path": str(reference)}],
            )
        )


def test_role_preserving_reference_input_must_be_readable(tmp_path):
    unreadable = tmp_path / "broken.png"
    unreadable.write_text("not an image", encoding="utf-8")

    with pytest.raises(source_generate.SourceGenerateError, match="not readable"):
        source_generate.load_spec(
            make_spec(
                tmp_path,
                reference_inputs=[{"role": "style", "path": str(unreadable)}],
            )
        )


@pytest.mark.parametrize(
    ("aspect_ratio", "expected_size"),
    [
        ("16:9", "1536x864"),
        ("9:16", "864x1536"),
        ("3:2", "1536x1024"),
    ],
)
def test_openai_size_preserves_supported_aspect_ratios(aspect_ratio, expected_size):
    size, _cost = source_generate._openai_size("1K", aspect_ratio)

    assert size == expected_size


def test_openai_rejects_more_than_sixteen_reference_images(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(
        make_spec(
            tmp_path,
            model="openai:gpt-image-2",
            reference_images=write_refs(tmp_path, 17),
        )
    )

    with pytest.raises(source_generate.SourceGenerateError, match="at most 16"):
        source_generate._generate_openai(spec, Path(spec["source_path"]), "gpt-image-2")


def test_generate_source_does_not_write_report_when_validation_fails(
    tmp_path,
    monkeypatch,
):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(
        make_spec(
            tmp_path,
            report_path=".godotmaker/asset-generation/reports/coin_source.json",
        )
    )

    def fake_grok(_spec_data, output, _model_name):
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text("not an image", encoding="utf-8")

    monkeypatch.setattr(source_generate, "_generate_grok", fake_grok)

    with pytest.raises(source_generate.SourceGenerateError, match="readable image"):
        source_generate.generate_source(spec)

    assert not (tmp_path / ".godotmaker" / "asset-generation" / "reports" / "coin_source.json").exists()


def test_generate_source_rejects_runtime_native_selectors(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    spec = source_generate.load_spec(make_spec(tmp_path, model="codex"))

    with pytest.raises(source_generate.SourceGenerateError, match="runtime-native"):
        source_generate.generate_source(spec)


def test_cli_outputs_json_error(tmp_path):
    spec_path = make_spec(tmp_path, model="native")

    result = subprocess.run(
        [
            sys.executable,
            str(TOOLS_DIR / "asset_source_generate.py"),
            "--spec",
            str(spec_path),
        ],
        capture_output=True,
        text=True,
        check=False,
        cwd=tmp_path,
    )

    assert result.returncode == 1
    data = json.loads(result.stdout)
    assert data["ok"] is False
    assert "runtime-native" in data["error"]
