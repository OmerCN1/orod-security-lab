import ssl

from app import build_context


def test_build_context_returns_a_context() -> None:
    assert isinstance(build_context(), ssl.SSLContext)
