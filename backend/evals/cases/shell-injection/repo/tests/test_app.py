from app import echo_value


def test_echo_value_round_trips() -> None:
    assert echo_value("hello") == "hello"
