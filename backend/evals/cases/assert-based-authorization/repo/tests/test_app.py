from app import authorize


def test_authorize_admin() -> None:
    assert authorize("admin") == "granted"
