from app import parse_document


def test_parse_document_lists_child_tags() -> None:
    assert parse_document("<root><a/><b/></root>") == ["a", "b"]
