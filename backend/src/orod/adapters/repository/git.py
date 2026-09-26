from __future__ import annotations

import ast
import json
import re
import shutil
import sys
import tomllib
from pathlib import Path

from orod.adapters.repository.patches import patch_targets
from orod.config import Settings
from orod.domain.errors import InvalidRepositoryError, PatchRejectedError, UnsafePathError
from orod.domain.models import (
    DEMO_REPOSITORY_RE,
    CommandResult,
    FileEntry,
    PackageDependency,
    PatchProposal,
    RepositorySnapshot,
    ValidationResult,
)
from orod.ports.execution import CommandRunner

GITHUB_REPO_RE = re.compile(
    r"^https://github\.com/(?P<owner>[A-Za-z0-9_.-]+)/(?P<repo>[A-Za-z0-9_.-]+?)(?:\.git)?$"
)
REQUIREMENT_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*(?:==\s*([^\s;]+))?")
IGNORED_PARTS = {
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
}
SECRET_NAMES = {".env", ".env.local", "id_rsa", "id_ed25519", ".npmrc", ".pypirc"}


class GitRepositoryAdapter:
    def __init__(
        self,
        settings: Settings,
        runner: CommandRunner,
        validation_runner: CommandRunner | None = None,
    ) -> None:
        self._settings = settings
        self._runner = runner
        self._workspace_root = settings.workspace_root.expanduser().resolve()
        self._validation_runner = validation_runner

    async def prepare(
        self,
        repository_url: str,
        base_branch: str | None,
        run_id: str,
        trusted: bool,
    ) -> RepositorySnapshot:
        target = (self._workspace_root / run_id).resolve()
        self._assert_under_workspace(target)
        if target.exists():
            raise InvalidRepositoryError("run workspace already exists")

        demo_match = DEMO_REPOSITORY_RE.fullmatch(repository_url)
        if demo_match is not None:
            slug = demo_match.group(1)
            source = self._resolve_fixture(slug)
            shutil.copytree(source, target)
            await self._initialize_demo_git(target)
            permission = "LOCAL"
            owner_repo = f"demo/{slug}"
            branch = base_branch or "main"
        else:
            match = GITHUB_REPO_RE.fullmatch(repository_url)
            if match is None:
                raise InvalidRepositoryError("only HTTPS github.com repository URLs are supported")
            metadata = await self._github_metadata(repository_url)
            permission = str(metadata.get("viewerPermission", "NONE"))
            if permission not in {"ADMIN", "MAINTAIN", "WRITE"}:
                raise InvalidRepositoryError("authenticated GitHub user has no push permission")
            raw_branch_ref = metadata.get("defaultBranchRef")
            branch_ref = raw_branch_ref if isinstance(raw_branch_ref, dict) else {}
            branch = base_branch or str(branch_ref.get("name") or "main")
            owner_repo = str(metadata.get("nameWithOwner") or match.group(0))
            target.parent.mkdir(parents=True, exist_ok=True)
            result = await self._runner.run(
                [
                    "gh",
                    "repo",
                    "clone",
                    repository_url,
                    str(target),
                    "--",
                    "--depth=1",
                    f"--branch={branch}",
                ],
                self._workspace_root,
            )
            if result.return_code != 0:
                raise InvalidRepositoryError(self._safe_error(result, "repository clone failed"))

        files = self._inventory_files(target)
        dependencies = self._discover_dependencies(target)
        summary = self._summarize_python(target, files, dependencies)
        return RepositorySnapshot(
            repository_url=repository_url,
            owner_repo=owner_repo,
            base_branch=branch,
            workspace_path=str(target),
            permission=permission,
            trusted=trusted,
            files=files,
            dependencies=dependencies,
            summary=summary,
        )

    async def read_files(
        self, snapshot: RepositorySnapshot, paths: list[str], max_chars: int = 30_000
    ) -> dict[str, str]:
        root = Path(snapshot.workspace_path).resolve()
        output: dict[str, str] = {}
        remaining = max_chars
        for relative in paths:
            path = self._safe_file(root, relative)
            if (
                path.name in SECRET_NAMES
                or path.is_symlink()
                or path.stat().st_size > self._settings.max_file_bytes
            ):
                continue
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if remaining <= 0:
                break
            output[relative] = content[:remaining]
            remaining -= len(output[relative])
        return output

    async def read_base_files(
        self, snapshot: RepositorySnapshot, paths: list[str], max_chars: int = 100_000
    ) -> dict[str, str]:
        """Read the pre-patch content of files from the workspace's HEAD commit.

        A generated patch is applied but never committed, so ``git show HEAD:<path>``
        still yields the original text. That is what lets the dashboard render a
        side-by-side diff without the API having to cache a copy of every file.
        """
        root = Path(snapshot.workspace_path).resolve()
        output: dict[str, str] = {}
        remaining = max_chars
        for relative in paths:
            if remaining <= 0:
                break
            if Path(relative).is_absolute() or ".." in Path(relative).parts:
                raise UnsafePathError("unsafe relative path")
            if Path(relative).name in SECRET_NAMES:
                continue
            # The command runner keeps only the *tail* of stdout once its limit is hit,
            # so it is given the same per-file budget the working-tree reader honours.
            # Without this a file above the runner's 20k default would come back missing
            # its beginning while the working side kept its head - the two sides of the
            # diff would not describe the same region of the file.
            result = await self._runner.run(
                ["git", "show", f"HEAD:{relative}"],
                root,
                max_output_chars=self._settings.max_file_bytes,
            )
            if result.return_code != 0:
                continue
            output[relative] = result.stdout[:remaining]
            remaining -= len(output[relative])
        return output

    async def apply_patch(self, snapshot: RepositorySnapshot, patch: PatchProposal) -> str:
        root = Path(snapshot.workspace_path).resolve()
        self._validate_patch(root, patch)
        check = await self._runner.run(
            ["git", "apply", "--check", "-"], root, input_text=patch.unified_diff
        )
        if check.return_code != 0:
            raise PatchRejectedError(self._safe_error(check, "git rejected generated patch"))
        apply_result = await self._runner.run(
            ["git", "apply", "-"], root, input_text=patch.unified_diff
        )
        if apply_result.return_code != 0:
            raise PatchRejectedError(self._safe_error(apply_result, "patch application failed"))
        diff = await self._runner.run(["git", "diff", "--"], root)
        if not diff.stdout.strip():
            raise PatchRejectedError("patch produced no repository changes")
        return diff.stdout

    async def validate(self, snapshot: RepositorySnapshot) -> ValidationResult:
        root = Path(snapshot.workspace_path).resolve()
        if not snapshot.trusted:
            return ValidationResult(
                passed=False,
                summary="Validation refused: repository was not explicitly marked trusted.",
            )

        commands: list[CommandResult] = []
        checks = [
            [sys.executable, "-m", "compileall", "-q", "."],
            [sys.executable, "-m", "ruff", "check", "--select", "F", "."],
            [sys.executable, "-m", "bandit", "-r", ".", "-f", "json", "-lll"],
        ]
        if (root / "tests").exists():
            checks.append([sys.executable, "-m", "pytest", "-q"])

        # Only server-owned fixtures may execute locally, and still require explicit trust.
        local_fixture = snapshot.permission == "LOCAL" and bool(
            DEMO_REPOSITORY_RE.fullmatch(snapshot.repository_url)
        )
        runner = self._runner if local_fixture else self._validation_runner
        if runner is None:
            return ValidationResult(passed=False, summary="Isolated validation is not configured.")
        for argv in checks:
            result = await runner.run(argv, root)
            commands.append(result)
            if result.return_code != 0 or result.timed_out:
                break

        if not local_fixture and commands[-1].return_code == 125:
            return ValidationResult(
                passed=False,
                commands=commands,
                summary="Container validation unavailable. Start Docker and build its image.",
            )

        residual_shell_true = self._count_shell_true(root)
        passed = all(item.return_code == 0 and not item.timed_out for item in commands)
        passed = passed and residual_shell_true == 0
        return ValidationResult(
            passed=passed,
            commands=commands,
            new_high_findings=residual_shell_true,
            summary=(
                "All fixed validation commands passed."
                if passed
                else "One or more validation checks failed; no pull request will be opened."
            ),
        )

    async def _github_metadata(self, repository_url: str) -> dict[str, object]:
        result = await self._runner.run(
            [
                "gh",
                "repo",
                "view",
                repository_url,
                "--json",
                "nameWithOwner,viewerPermission,defaultBranchRef",
            ],
            self._workspace_root,
        )
        if result.return_code != 0:
            raise InvalidRepositoryError(self._safe_error(result, "GitHub authentication failed"))
        try:
            value = json.loads(result.stdout)
        except json.JSONDecodeError as exc:
            raise InvalidRepositoryError("GitHub CLI returned invalid metadata") from exc
        if not isinstance(value, dict):
            raise InvalidRepositoryError("GitHub CLI returned unexpected metadata")
        return value

    def _resolve_fixture(self, slug: str) -> Path:
        """Map a ``demo://<slug>`` URL onto a directory beneath the fixture root.

        Candidates are tried in order so both the eval corpus layout
        (``<slug>/repo``) and the plain test-fixture layout resolve, while every
        candidate is still verified to stay inside the configured fixture root.
        """
        root = self._settings.fixture_root.expanduser().resolve()
        underscored = slug.replace("-", "_")
        candidates = (
            root / slug / "repo",
            root / slug,
            root / underscored,
            root / f"{underscored}_repo",
        )
        for candidate in candidates:
            resolved = candidate.resolve()
            if resolved.is_relative_to(root) and resolved.is_dir():
                return resolved
        raise InvalidRepositoryError(f"demo fixture is missing: {slug}")

    async def _initialize_demo_git(self, target: Path) -> None:
        commands = [
            ["git", "init", "-b", "main"],
            ["git", "config", "user.email", "orod@example.invalid"],
            ["git", "config", "user.name", "OROD Demo"],
            ["git", "add", "."],
            ["git", "commit", "-m", "test: vulnerable demo baseline"],
        ]
        for argv in commands:
            result = await self._runner.run(argv, target)
            if result.return_code != 0:
                raise InvalidRepositoryError(
                    self._safe_error(result, "demo Git initialization failed")
                )

    def _inventory_files(self, root: Path) -> list[FileEntry]:
        files: list[FileEntry] = []
        for path in sorted(root.rglob("*")):
            relative = path.relative_to(root)
            if any(part in IGNORED_PARTS for part in relative.parts):
                continue
            if path.is_symlink() or not path.is_file() or path.name in SECRET_NAMES:
                continue
            size = path.stat().st_size
            if size > self._settings.max_file_bytes:
                continue
            language = "python" if path.suffix == ".py" else None
            files.append(FileEntry(path=relative.as_posix(), size=size, language=language))
        return files[:2_000]

    def _discover_dependencies(self, root: Path) -> list[PackageDependency]:
        found: dict[str, PackageDependency] = {}

        def remember(item: PackageDependency) -> None:
            key = item.name.lower().replace("_", "-")
            current = found.get(key)
            if current is None or (item.version is not None and current.version is None):
                found[key] = item

        pyproject = root / "pyproject.toml"
        if pyproject.exists() and pyproject.stat().st_size <= self._settings.max_file_bytes:
            try:
                data = tomllib.loads(pyproject.read_text())
                for raw in data.get("project", {}).get("dependencies", []):
                    match = REQUIREMENT_RE.match(str(raw))
                    if match:
                        remember(
                            PackageDependency(
                                name=match.group(1),
                                version=match.group(2),
                                source_file="pyproject.toml",
                            )
                        )
            except (tomllib.TOMLDecodeError, OSError):
                pass

        for requirements in root.glob("*requirements*.txt"):
            for line in requirements.read_text(errors="ignore").splitlines():
                match = REQUIREMENT_RE.match(line)
                if match and not line.lstrip().startswith(("#", "-")):
                    remember(
                        PackageDependency(
                            name=match.group(1),
                            version=match.group(2),
                            source_file=requirements.name,
                        )
                    )

        for lock_name in ("uv.lock", "poetry.lock"):
            lock_file = root / lock_name
            if not lock_file.exists() or lock_file.stat().st_size > self._settings.max_file_bytes:
                continue
            try:
                data = tomllib.loads(lock_file.read_text())
                for package in data.get("package", []):
                    if not isinstance(package, dict) or not package.get("name"):
                        continue
                    remember(
                        PackageDependency(
                            name=str(package["name"]),
                            version=str(package["version"]) if package.get("version") else None,
                            source_file=lock_name,
                        )
                    )
            except (tomllib.TOMLDecodeError, OSError):
                pass
        return sorted(found.values(), key=lambda item: item.name.lower())

    def _summarize_python(
        self,
        root: Path,
        files: list[FileEntry],
        dependencies: list[PackageDependency],
    ) -> str:
        modules = 0
        imports: set[str] = set()
        functions = 0
        classes = 0
        for entry in files:
            if entry.language != "python":
                continue
            modules += 1
            try:
                tree = ast.parse((root / entry.path).read_text())
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, (ast.Import, ast.ImportFrom)):
                    if isinstance(node, ast.Import):
                        imports.update(alias.name.split(".")[0] for alias in node.names)
                    elif node.module:
                        imports.add(node.module.split(".")[0])
                elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    functions += 1
                elif isinstance(node, ast.ClassDef):
                    classes += 1
        return (
            f"Python repository with {modules} modules, {functions} functions, "
            f"{classes} classes and {len(dependencies)} declared dependencies. "
            f"Top imports: {', '.join(sorted(imports)[:12]) or 'none'}."
        )

    def _validate_patch(self, root: Path, patch: PatchProposal) -> None:
        if len(patch.unified_diff.splitlines()) > self._settings.max_diff_lines:
            raise PatchRejectedError("patch exceeds configured line limit")
        if len(patch.unified_diff.encode("utf-8")) > self._settings.max_file_bytes:
            raise PatchRejectedError("patch exceeds configured byte limit")
        if not patch.changed_files:
            raise PatchRejectedError("patch has no changed files")
        targets = patch_targets(patch.unified_diff)
        if len(set(patch.changed_files)) != len(patch.changed_files):
            raise PatchRejectedError("duplicate declared patch target")
        if targets != set(patch.changed_files):
            raise PatchRejectedError("diff targets do not match changed_files")
        for relative in patch.changed_files:
            try:
                path = self._safe_file(root, relative)
            except UnsafePathError as exc:
                raise PatchRejectedError("unsafe patch target") from exc
            if path.name in SECRET_NAMES or any(
                part.startswith(".") for part in Path(relative).parts
            ):
                raise PatchRejectedError(f"unsafe patch target: {relative}")
            if path.suffix not in {".py", ".toml", ".txt", ".lock"}:
                raise PatchRejectedError(f"unsupported patch target: {relative}")
            if path.stat().st_size > self._settings.max_file_bytes:
                raise PatchRejectedError("patch target exceeds configured byte limit")
            try:
                content = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError) as exc:
                raise PatchRejectedError("patch target is not readable text") from exc
            if "\x00" in content:
                raise PatchRejectedError("binary patch target")

    def _safe_file(self, root: Path, relative: str) -> Path:
        if Path(relative).is_absolute() or ".." in Path(relative).parts:
            raise UnsafePathError("unsafe relative path")
        candidate = root
        for part in Path(relative).parts:
            candidate = candidate / part
            if candidate.is_symlink():
                raise UnsafePathError("symlink file or parent directory")
        path = (root / relative).resolve()
        if not path.is_relative_to(root) or not path.exists() or not path.is_file():
            raise UnsafePathError("file is outside workspace or missing")
        return path

    def _assert_under_workspace(self, path: Path) -> None:
        if not path.is_relative_to(self._workspace_root):
            raise UnsafePathError("path escaped workspace root")

    @staticmethod
    def _safe_error(result: CommandResult, fallback: str) -> str:
        text = (result.stderr or result.stdout).strip().splitlines()
        return text[-1][:500] if text else fallback

    @staticmethod
    def _count_shell_true(root: Path) -> int:
        count = 0
        for path in root.rglob("*.py"):
            if any(part in IGNORED_PARTS for part in path.relative_to(root).parts):
                continue
            try:
                tree = ast.parse(path.read_text())
            except (SyntaxError, UnicodeDecodeError, OSError):
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    count += sum(
                        1
                        for keyword in node.keywords
                        if keyword.arg == "shell"
                        and isinstance(keyword.value, ast.Constant)
                        and keyword.value.value is True
                    )
        return count
