"""Tests for migrations/20260610061543_add_asset_producer_model.py."""
import importlib.util
from pathlib import Path

import pytest


MIGRATION_PATH = (
    Path(__file__).resolve().parents[2]
    / "migrations"
    / "20260610061543_add_asset_producer_model.py"
)


@pytest.fixture
def migration_module():
    spec = importlib.util.spec_from_file_location("asset_producer_model", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_adds_missing_asset_producer_model_after_worker_model(
    migration_module, tmp_path
):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.parent.mkdir()
    config.write_text(
        "worker_model: opus\n"
        "verifier_model: sonnet\n",
        encoding="utf-8",
    )

    migration_module.migrate(tmp_path)

    lines = config.read_text(encoding="utf-8").splitlines()
    assert "asset_producer_model: sonnet" in lines
    assert lines.index("asset_producer_model: sonnet") == lines.index(
        "worker_model: opus"
    ) + 1


def test_preserves_existing_asset_producer_model(migration_module, tmp_path):
    config = tmp_path / ".godotmaker" / "config.yaml"
    config.parent.mkdir()
    config.write_text("asset_producer_model: opus\n", encoding="utf-8")

    migration_module.migrate(tmp_path)

    assert config.read_text(encoding="utf-8") == "asset_producer_model: opus\n"


def test_creates_config_when_missing(migration_module, tmp_path):
    migration_module.migrate(tmp_path)

    config = tmp_path / ".godotmaker" / "config.yaml"
    assert "asset_producer_model: sonnet" in config.read_text(encoding="utf-8")
