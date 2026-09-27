"""Which languages a repository's source files are written in, judged by extension."""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import PurePosixPath

from orod.domain.models import FileEntry

PYTHON = "Python"
SOURCE_LANGUAGES = {
    ".py": PYTHON,
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".mjs": "JavaScript",
    ".cjs": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".go": "Go",
    ".java": "Java",
    ".kt": "Kotlin",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".php": "PHP",
    ".cs": "C#",
    ".swift": "Swift",
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".scala": "Scala",
    ".dart": "Dart",
}


@dataclass(frozen=True)
class LanguageProfile:
    source_files: dict[str, int]

    @property
    def python_files(self) -> int:
        return self.source_files.get(PYTHON, 0)

    @property
    def dominant(self) -> str | None:
        """The language with the most source files; ties resolve alphabetically."""
        if not self.source_files:
            return None
        return min(self.source_files, key=lambda name: (-self.source_files[name], name))

    def describe(self, limit: int = 3) -> str:
        ranked = sorted(self.source_files.items(), key=lambda item: (-item[1], item[0]))
        return ", ".join(f"{name} ({count})" for name, count in ranked[:limit]) or "no source"


def profile_languages(files: Iterable[FileEntry]) -> LanguageProfile:
    counts = Counter(
        SOURCE_LANGUAGES[suffix]
        for entry in files
        if (suffix := PurePosixPath(entry.path).suffix.lower()) in SOURCE_LANGUAGES
    )
    return LanguageProfile(source_files=dict(counts))
