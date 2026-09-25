from app import dump_cache, load_cache


def test_cache_round_trip() -> None:
    assert load_cache(dump_cache({"a": 1, "b": 2})) == {"a": 1, "b": 2}
