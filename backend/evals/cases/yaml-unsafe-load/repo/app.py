import yaml


def load_config(raw: str) -> dict[str, object]:
    return dict(yaml.load(raw, Loader=yaml.Loader))
