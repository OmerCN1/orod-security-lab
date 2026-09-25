import pickle


def dump_cache(values: dict[str, int]) -> bytes:
    return pickle.dumps(values)


def load_cache(blob: bytes) -> dict[str, int]:
    return dict(pickle.loads(blob))
