from orod.adapters.llm.prompts import build_patch_prompt
from orod.domain.models import RepositorySnapshot
from orod.graph.builder import describe_previous_attempt

PATCH = {"unified_diff": "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-shell=True\n+shell=False\n"}
FAILED = {"passed": False, "summary": "Patch did not resolve selected findings: B607 in app.py"}


def test_a_repair_tells_the_model_its_attempt_was_discarded_and_what_remains() -> None:
    text = describe_previous_attempt(PATCH, FAILED, regenerating=False)

    assert text is not None
    assert "B607 in app.py" in text
    assert "back at its original content" in text
    assert "+shell=False" in text
    assert "every listed finding" in text


def test_a_passing_attempt_is_not_presented_as_a_validation_error() -> None:
    passed = {"passed": True, "summary": "All fixed validation checks passed."}

    text = describe_previous_attempt(PATCH, passed, regenerating=True)

    assert text is not None
    assert "reviewer asked for a different patch" in text
    assert "Validation rejected" not in text


def test_a_rejected_proposal_passes_on_only_its_reason() -> None:
    rejected = {"passed": False, "summary": "Patch rejected: edit 1 search text was not found"}

    assert describe_previous_attempt(None, rejected, regenerating=False) == rejected["summary"]
    assert describe_previous_attempt(None, None, regenerating=False) is None
    assert describe_previous_attempt(None, {"passed": True, "summary": "ok"}, False) is None


def test_the_prompt_labels_it_as_the_previous_attempt() -> None:
    snapshot = RepositorySnapshot(repository_url="demo://x", workspace_path="workspaces/x")

    prompt = build_patch_prompt(snapshot, [], {}, "discarded attempt")

    assert "Previous attempt: discarded attempt" in prompt
