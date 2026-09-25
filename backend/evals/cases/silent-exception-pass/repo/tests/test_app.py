from app import parse_or_default


def test_parse_or_default_handles_both_paths() -> None:
    assert parse_or_default('{"b": 2}', {}) == {"b": 2}
    assert parse_or_default("{not json", {"a": 1}) == {"a": 1}
