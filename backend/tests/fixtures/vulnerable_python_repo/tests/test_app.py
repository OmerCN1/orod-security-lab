from app import echo_user


def test_echo_user() -> None:
    assert echo_user("hello") == "hello"
