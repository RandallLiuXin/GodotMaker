from pathlib import Path
import sys

TOOLS_DIR = Path(__file__).resolve().parents[2] / "tools"
sys.path.insert(0, str(TOOLS_DIR))

from asset_user_preflight import find_user_asset_candidates  # noqa: E402


def write_assets_md(root: Path) -> None:
    (root / "ASSETS.md").write_text(
        "# Assets\n\n"
        "## Asset Table\n\n"
        "| ID | Tag | Name | Type | Size | Params | File Path | Status |\n"
        "|---|---|---|---|---|---|---|---|\n"
        "| 1 | v0.1.0 | player | sprite | 32x32 | user | assets/player.png | MISSING |\n"
        "| 2 | v0.1.0 | enemy | sprite | 32x32 | gen | assets/enemy.png | generated |\n"
        "| 3 | v0.1.0 | jump | audio | 1s | user | assets/audio/jump.wav | deferred |\n",
        encoding="utf-8",
    )


def test_detects_unconsumed_image_and_audio_candidates(tmp_path: Path):
    write_assets_md(tmp_path)
    (tmp_path / "assets" / "audio").mkdir(parents=True)
    (tmp_path / "assets" / "player.png").write_bytes(b"image")
    (tmp_path / "assets" / "ui.webp").write_bytes(b"image")
    (tmp_path / "assets" / "audio" / "hit.ogg").write_bytes(b"audio")
    (tmp_path / "assets" / "audio" / "jump.wav").write_bytes(b"audio")
    (tmp_path / "assets" / "enemy.png").write_bytes(b"generated")
    (tmp_path / "assets" / "notes.txt").write_text("ignore", encoding="utf-8")

    result = find_user_asset_candidates(tmp_path)

    assert result["needs_analyst"] is True
    assert result["image_candidate_count"] == 2
    assert result["audio_candidate_count"] == 2
    paths = {item["path"] for item in result["candidates"]}
    assert paths == {
        "assets/player.png",
        "assets/ui.webp",
        "assets/audio/hit.ogg",
        "assets/audio/jump.wav",
    }
    player = next(item for item in result["candidates"] if item["path"] == "assets/player.png")
    assert player["match_kind"] == "exact_path"
    assert player["matched_asset_id"] == "player"
    assert player["matched_status"] == "MISSING"


def test_excludes_manifest_paths_and_origin_archives(tmp_path: Path):
    (tmp_path / "ASSETS.md").write_text("# Assets\n", encoding="utf-8")
    (tmp_path / "assets" / "origin").mkdir(parents=True)
    (tmp_path / "assets" / "hero.png").write_bytes(b"image")
    (tmp_path / "assets" / "known.png").write_bytes(b"image")
    (tmp_path / "assets" / "origin" / "old.png").write_bytes(b"image")
    (tmp_path / "assets" / "manifest.json").write_text(
        '{"assets": [{"path": "assets/known.png"}]}',
        encoding="utf-8",
    )

    result = find_user_asset_candidates(tmp_path)

    paths = [item["path"] for item in result["candidates"]]
    assert paths == ["assets/hero.png"]
    assert result["consumed_paths"] == ["assets/known.png"]


def test_excludes_real_analyst_manifest_file_schema(tmp_path: Path):
    (tmp_path / "ASSETS.md").write_text("# Assets\n", encoding="utf-8")
    (tmp_path / "assets" / "sprites").mkdir(parents=True)
    (tmp_path / "assets" / "sprites" / "player.png").write_bytes(b"image")
    (tmp_path / "assets" / "sprites" / "enemy.png").write_bytes(b"image")
    (tmp_path / "assets" / "manifest.json").write_text(
        '{"assets": [{"file": "sprites/player.png"}]}',
        encoding="utf-8",
    )

    result = find_user_asset_candidates(tmp_path)

    paths = [item["path"] for item in result["candidates"]]
    assert paths == ["assets/sprites/enemy.png"]
    assert result["consumed_paths"] == ["assets/sprites/player.png"]


def test_excludes_utf8_bom_manifest_paths(tmp_path: Path):
    (tmp_path / "ASSETS.md").write_text("# Assets\n", encoding="utf-8")
    (tmp_path / "assets" / "sprites").mkdir(parents=True)
    (tmp_path / "assets" / "sprites" / "known.png").write_bytes(b"image")
    (tmp_path / "assets" / "sprites" / "new.png").write_bytes(b"image")
    (tmp_path / "assets" / "manifest.json").write_text(
        '{"assets": [{"file": "sprites/known.png"}]}',
        encoding="utf-8-sig",
    )

    result = find_user_asset_candidates(tmp_path)

    paths = [item["path"] for item in result["candidates"]]
    assert paths == ["assets/sprites/new.png"]
    assert result["warnings"] == []
    assert result["consumed_paths"] == ["assets/sprites/known.png"]


def test_detects_svg_as_image_candidate(tmp_path: Path):
    (tmp_path / "ASSETS.md").write_text("# Assets\n", encoding="utf-8")
    (tmp_path / "assets" / "ui").mkdir(parents=True)
    (tmp_path / "assets" / "ui" / "button.svg").write_text("<svg />", encoding="utf-8")

    result = find_user_asset_candidates(tmp_path)

    assert result["needs_analyst"] is True
    assert result["image_candidate_count"] == 1
    assert result["candidates"][0]["path"] == "assets/ui/button.svg"
    assert result["candidates"][0]["kind_hint"] == "image"


def test_audio_only_candidates_do_not_require_analyst(tmp_path: Path):
    (tmp_path / "ASSETS.md").write_text("# Assets\n", encoding="utf-8")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "theme.mp3").write_bytes(b"audio")

    result = find_user_asset_candidates(tmp_path)

    assert result["candidate_count"] == 1
    assert result["image_candidate_count"] == 0
    assert result["audio_candidate_count"] == 1
    assert result["needs_analyst"] is False
