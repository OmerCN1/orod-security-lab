from app import list_directory


def test_list_directory_returns_text() -> None:
    assert isinstance(list_directory("."), str)
