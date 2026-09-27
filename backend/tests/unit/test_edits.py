import pytest

from orod.adapters.repository.edits import apply_edits, render_diff, unified_diff
from orod.adapters.repository.patches import patch_targets
from orod.domain.errors import PatchRejectedError
from orod.domain.models import FileEdit

SOURCE = "import subprocess\n\n\ndef echo(value):\n    return subprocess.run(value, shell=True)\n"


def edit(search: str, replace: str, path: str = "app.py") -> FileEdit:
    return FileEdit(path=path, search=search, replace=replace)


def test_an_exact_unique_excerpt_is_replaced() -> None:
    changed = apply_edits({"app.py": SOURCE}, [edit("shell=True", "shell=False")])

    assert changed["app.py"] == SOURCE.replace("shell=True", "shell=False")


def test_edits_apply_in_order_to_the_updated_text() -> None:
    changed = apply_edits(
        {"app.py": SOURCE},
        [
            edit("import subprocess\n", "import shlex\nimport subprocess\n"),
            edit("run(value, shell=True)", "run(shlex.split(value))"),
        ],
    )

    assert changed["app.py"].startswith("import shlex\nimport subprocess\n")
    assert "run(shlex.split(value))" in changed["app.py"]


def test_trailing_whitespace_drift_in_the_search_still_matches_whole_lines() -> None:
    # Models often copy a line with stray trailing spaces and add a final newline.
    search = "def echo(value):   \n    return subprocess.run(value, shell=True)  \n"
    replace = "def echo(value):\n    return subprocess.run([value])\n"

    changed = apply_edits({"app.py": SOURCE}, [edit(search, replace)])

    assert changed["app.py"].endswith("def echo(value):\n    return subprocess.run([value])\n")
    assert "\n\n\n\n" not in changed["app.py"]


def test_an_ambiguous_search_is_rejected() -> None:
    source = "value = 1\nvalue = 1\n"
    with pytest.raises(PatchRejectedError, match="occurs 2 times"):
        apply_edits({"app.py": source}, [edit("value = 1", "value = 2")])


def test_a_missing_search_is_rejected() -> None:
    with pytest.raises(PatchRejectedError, match="not found"):
        apply_edits({"app.py": SOURCE}, [edit("shell = True", "shell=False")])


def test_indentation_is_not_guessed() -> None:
    # The body is indented by two spaces here but four in the file.
    search = "def echo(value):\n  return subprocess.run(value, shell=True)\n"
    with pytest.raises(PatchRejectedError, match="not found"):
        apply_edits({"app.py": SOURCE}, [edit(search, "def echo(value):\n  return 1\n")])


@pytest.mark.parametrize(
    ("edits", "reason"),
    [
        ([], "no edits"),
        ([edit("   ", "x")], "empty search"),
        ([edit("shell=True", "shell=True")], "no repository changes"),
        ([edit("x", "y", path="other.py")], "not supplied"),
    ],
)
def test_unusable_proposals_are_rejected(edits: list[FileEdit], reason: str) -> None:
    with pytest.raises(PatchRejectedError, match=reason):
        apply_edits({"app.py": SOURCE}, edits)


def test_rendered_diff_passes_the_strict_patch_parser() -> None:
    originals = {"app.py": SOURCE, "b.py": "value = 1"}
    changed = apply_edits(
        originals, [edit("shell=True", "shell=False"), edit("value = 1", "value = 2", "b.py")]
    )

    diff = render_diff(originals, changed)

    assert patch_targets(diff) == {"app.py", "b.py"}


def test_a_file_without_a_final_newline_is_marked() -> None:
    diff = unified_diff("b.py", "value = 1", "value = 2")

    assert diff.endswith("+value = 2\n\\ No newline at end of file\n")
    assert patch_targets(diff) == {"b.py"}
