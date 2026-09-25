from app import append_audit


def test_append_audit_returns_the_log_path() -> None:
    assert append_audit("checked").endswith("orod-audit.log")
