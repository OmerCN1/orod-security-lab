from app import session_token


def test_session_token_length() -> None:
    assert len(session_token(24)) == 24
