from orod.adapters.scanners.bandit import _title


def test_title_prefers_the_human_sentence_over_the_internal_slug() -> None:
    """Bandit's test_name is a slug; showing it is what produced titles like "blacklist"."""
    item = {
        "test_name": "subprocess_popen_with_shell_equals_true",
        "issue_text": "subprocess call with shell=True identified, security issue.",
    }
    assert _title(item, "B602") == "Subprocess call with shell=True identified, security issue"


def test_title_humanises_the_slug_when_there_is_no_issue_text() -> None:
    assert _title({"test_name": "start_process_with_partial_path"}, "B607") == (
        "Start process with partial path"
    )


def test_title_falls_back_to_the_rule_id_when_bandit_gives_nothing() -> None:
    assert _title({}, "B404") == "B404"


def test_title_is_bounded_so_one_finding_cannot_dominate_the_layout() -> None:
    assert len(_title({"issue_text": "x" * 400}, "B000")) == 120
