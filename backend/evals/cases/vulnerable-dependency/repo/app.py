"""Configuration loader for a small service."""

import yaml


def load_config(text: str) -> dict[str, object]:
    data = yaml.safe_load(text)
    return data if isinstance(data, dict) else {}
