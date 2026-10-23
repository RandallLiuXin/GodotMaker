#!/usr/bin/env python3
"""Canonical provider vocabulary for Asset Skill image generation."""
from __future__ import annotations


# Keep this tuple in user-facing order. Declarative schemas and documentation
# cannot import Python, so contract tests compare every published selector with
# this vocabulary.
ASSET_IMAGE_PROVIDERS = (
    "native",
    "codex",
    "gemini",
    "openai",
    "grok",
    "wan",
)
ASSET_IMAGE_PROVIDER_SET = frozenset(ASSET_IMAGE_PROVIDERS)
RUNTIME_IMAGE_PROVIDERS = frozenset({"native", "codex"})
API_IMAGE_PROVIDERS = ASSET_IMAGE_PROVIDER_SET - RUNTIME_IMAGE_PROVIDERS
MODEL_SELECTOR_TOKENS = ASSET_IMAGE_PROVIDER_SET | {"none"}


def provider_choices() -> str:
    """Return the canonical provider names for validation messages."""
    return ", ".join(ASSET_IMAGE_PROVIDERS)
