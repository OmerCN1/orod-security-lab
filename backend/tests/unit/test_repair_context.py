from orod.adapters.llm.prompts import build_patch_prompt
from orod.domain.diffs import split_by_file
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


COMBINED = (
    "diff --git a/app.py b/app.py\n"
    "index 1111111..2222222 100644\n"
    "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-eval(text)\n+literal_eval(text)\n"
    "diff --git a/requirements.txt b/requirements.txt\n"
    "index 3333333..4444444 100644\n"
    "--- a/requirements.txt\n+++ b/requirements.txt\n@@ -1 +1 @@\n"
    "-PyYAML==5.3.1\n+PyYAML==5.4\n"
)


def test_a_repair_shows_the_model_only_the_files_it_may_edit() -> None:
    # Before: the pin change OROD made itself was shown too, the model edited
    # requirements.txt, and the whole repair was rejected as editing an unsupplied file.
    text = describe_previous_attempt({"unified_diff": COMBINED}, FAILED, False, editable={"app.py"})

    assert text is not None
    assert "+literal_eval(text)" in text
    assert "requirements.txt" not in text


def test_a_dependency_only_attempt_shows_no_source_diff() -> None:
    text = describe_previous_attempt(
        {"unified_diff": COMBINED}, FAILED, False, editable={"other.py"}
    )

    assert text is not None
    assert "(none of the files below)" in text
    assert "PyYAML" not in text


def test_diffs_split_by_file_with_and_without_git_headers() -> None:
    sections = split_by_file(COMBINED)
    assert list(sections) == ["app.py", "requirements.txt"]
    assert sections["app.py"].startswith("diff --git a/app.py")
    assert "PyYAML" not in sections["app.py"]

    rendered = PATCH["unified_diff"] + "--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-x\n+y\n"
    assert split_by_file(rendered) == {
        "app.py": PATCH["unified_diff"],
        "b.py": "--- a/b.py\n+++ b/b.py\n@@ -1 +1 @@\n-x\n+y\n",
    }
