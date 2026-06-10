"""Add the asset-producer model selector to existing project configs."""
from pathlib import Path


KEY = "asset_producer_model"
DEFAULT = "sonnet"


def _parse_scalar_keys(text: str) -> set[str]:
    keys: set[str] = set()
    for raw_line in text.splitlines():
        if raw_line.startswith((" ", "\t")):
            continue
        line = raw_line.split("#", 1)[0].strip()
        if not line or ":" not in line:
            continue
        key, _value = line.split(":", 1)
        key = key.strip()
        if key:
            keys.add(key)
    return keys


def migrate(target: Path) -> None:
    config_path = target / ".godotmaker" / "config.yaml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    text = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
    keys = _parse_scalar_keys(text)

    if KEY in keys:
        print("  .godotmaker/config.yaml asset producer model already present")
        return

    lines = text.splitlines()
    if lines and lines[-1].strip():
        lines.append("")
    if "worker_model" in keys:
        insert_at = next(
            (
                index + 1
                for index, line in enumerate(lines)
                if line.split("#", 1)[0].strip().startswith("worker_model:")
            ),
            len(lines),
        )
        lines.insert(insert_at, f"{KEY}: {DEFAULT}")
    else:
        lines.extend([
            "# Agent model configuration",
            f"{KEY}: {DEFAULT}",
        ])

    config_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    print("  Updated .godotmaker/config.yaml asset producer model")
