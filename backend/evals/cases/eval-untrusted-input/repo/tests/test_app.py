from app import parse_setting


def test_parse_setting_reads_a_mapping() -> None:
    assert parse_setting("{'retries': 3}") == {"retries": 3}
