from app import fingerprint


def test_fingerprint_is_stable_hex() -> None:
    first = fingerprint(b"payload")
    assert first == fingerprint(b"payload")
    assert len(first) >= 32
