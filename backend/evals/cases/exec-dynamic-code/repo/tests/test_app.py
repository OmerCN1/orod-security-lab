from app import compute_total


def test_compute_total() -> None:
    assert compute_total(7, 3) == 21
