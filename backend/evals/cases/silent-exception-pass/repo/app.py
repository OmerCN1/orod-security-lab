import json


def parse_or_default(raw: str, default: dict[str, object]) -> dict[str, object]:
    try:
        return dict(json.loads(raw))
    except Exception:
        pass
    return default
