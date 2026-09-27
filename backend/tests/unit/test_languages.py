from orod.domain.languages import profile_languages
from orod.domain.models import FileEntry


def files(*paths: str) -> list[FileEntry]:
    return [FileEntry(path=path, size=1) for path in paths]


def test_source_files_are_counted_by_language() -> None:
    profile = profile_languages(files("app.py", "web/a.ts", "web/b.TSX", "README.md", "x.lock"))

    assert profile.source_files == {"Python": 1, "TypeScript": 2}
    assert profile.python_files == 1
    assert profile.dominant == "TypeScript"
    assert profile.describe() == "TypeScript (2), Python (1)"


def test_a_repository_without_source_files_has_no_dominant_language() -> None:
    profile = profile_languages(files("README.md", "docs/index.html"))

    assert profile.python_files == 0
    assert profile.dominant is None
    assert profile.describe() == "no source"
