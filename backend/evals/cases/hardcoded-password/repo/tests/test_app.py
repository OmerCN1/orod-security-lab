from app import connection_string


def test_connection_string_shape() -> None:
    value = connection_string("db.internal", "app")
    assert value.startswith("postgresql://app:")
    assert value.endswith("@db.internal/app")
