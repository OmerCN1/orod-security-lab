from __future__ import annotations

import ast
import json
import re
import shutil
import sys
import tomllib
from itertools import islice
from pathlib import Path

from orod.adapters.repository.files import RepositoryFiles
from orod.adapters.repository.patches import WORKING_DIFF_ARGV, patch_targets
from orod.config import Settings
from orod.domain.errors import (
    InvalidRepositoryError,
    PatchRejectedError,
    UnsafePathError,
    WorkspaceIntegrityError,
)
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
            shutil.copytree(source, target, symlinks=True)
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
        root = Path(snapshot.workspace_path)
        reader = self._files(root)
        output: dict[str, str] = {}
        remaining = max_chars
        for relative in paths:
            if remaining <= 0:
                break
            content = reader.read(relative).content
            output[relative] = content[:remaining]
            remaining -= len(output[relative])
        return output

    async def read_base_files(
        self, snapshot: RepositorySnapshot, paths: list[str], max_chars: int = 100_000
    ) -> dict[str, str]:
        """Read the pre-patch content of files from the workspace's HEAD commit.

        Git tree mode and blob size are checked before reading the original content.
        The working path is subject to the same policy as other repository reads.
        """
        root = Path(snapshot.workspace_path)
        reader = self._files(root)
        output: dict[str, str] = {}
        remaining = max_chars
        for relative in paths:
            if remaining <= 0:
                break
            # Both revisions enforce the same working-path policy. Also check the
            # Git blob itself: a safe working file may have an unsafe base revision.
            reader.read(relative)
            metadata = await self._runner.run(
                ["git", "ls-tree", "--full-tree", "-z", "HEAD", "--", relative], root
            )
            if metadata.return_code != 0 or metadata.timed_out or not metadata.stdout:
                continue
            header, separator, name = metadata.stdout.removesuffix("\x00").partition("\t")
            fields = header.split()
            if (
                not separator
                or name != relative
                or len(fields) != 3
                or fields[0] not in {"100644", "100755"}
                or fields[1] != "blob"
                or re.fullmatch(r"[a-f0-9]{40,64}", fields[2]) is None
            ):
                raise UnsafePathError("base revision is not a regular file")
            object_id = fields[2]
            size_result = await self._runner.run(["git", "cat-file", "-s", object_id], root)
            try:
                size = int(size_result.stdout.strip())
            except ValueError as exc:
                raise UnsafePathError("base file size is unavailable") from exc
            if (
                size_result.return_code != 0
                or size_result.timed_out
                or not 0 <= size <= reader.max_file_bytes
            ):
                raise UnsafePathError("base file exceeds configured byte limit or is unavailable")
            result = await self._runner.run(
                ["git", "cat-file", "blob", object_id],
                root,
                max_output_chars=reader.max_file_bytes + 1,
            )
            if result.return_code != 0 or result.timed_out:
                continue
            # CommandRunner decodes stdout with replacement. Refuse lossy decoding
            # rather than letting a binary Git blob masquerade as a text file.
            encoded = result.stdout.encode("utf-8")
            if "\ufffd" in result.stdout or len(encoded) != size:
                raise UnsafePathError("base file is not complete UTF-8 text")
            output[relative] = reader.decode_text(encoded)[:remaining]
            remaining -= len(output[relative])
        return output

    async def apply_patch(self, snapshot: RepositorySnapshot, patch: PatchProposal) -> str:
        """Apply a patch to a workspace that is still at its base revision.

        Starting from the base is what makes the returned diff equal to this proposal
        alone; a leftover earlier attempt would otherwise be validated and shown but not
        published with it.
        """
        root = Path(snapshot.workspace_path)
        self._validate_patch(root, patch)
        if await self._working_diff(root):
            raise WorkspaceIntegrityError("workspace already carries changes before a new patch")
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
        diff = await self._working_diff(root)
        if not diff.strip():
            raise PatchRejectedError("patch produced no repository changes")
        return diff

    async def revert_patch(self, snapshot: RepositorySnapshot, applied_diff: str) -> None:
        """Return the workspace to its base revision by reversing a patch OROD applied.

        Only the exact diff recorded at apply time is reversed; anything else in the
        working tree is an integrity failure rather than something to clean up. A
        workspace that is already clean is left alone, so a re-executed graph node can
        call this again safely.
        """
        root = Path(snapshot.workspace_path)
        current = await self._working_diff(root)
        if not current:
            return
        if current != applied_diff:
            raise WorkspaceIntegrityError("workspace changed after the patch was applied")
        for argv in (["git", "apply", "-R", "--check", "-"], ["git", "apply", "-R", "-"]):
            result = await self._runner.run(argv, root, input_text=applied_diff)
            if result.return_code != 0 or result.timed_out:
                raise WorkspaceIntegrityError(self._safe_error(result, "patch revert failed"))
        if await self._working_diff(root):
            raise WorkspaceIntegrityError("workspace still differs from its base after revert")

    async def _working_diff(self, root: Path) -> str:
        limit = self._settings.max_file_bytes
        result = await self._runner.run(list(WORKING_DIFF_ARGV), root, max_output_chars=limit + 1)
        if result.return_code != 0 or result.timed_out:
            raise WorkspaceIntegrityError(self._safe_error(result, "workspace diff failed"))
        # The runner keeps the tail of oversized output; never treat a tail as the diff.
        if len(result.stdout) > limit:
            raise WorkspaceIntegrityError("workspace diff exceeds configured byte limit")
        return result.stdout

    async def validate(self, snapshot: RepositorySnapshot) -> ValidationResult:
        root = Path(snapshot.workspace_path)
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
        return [
            FileEntry(
                path=item.relative,
                size=item.size,
                language="python" if Path(item.relative).suffix == ".py" else None,
            )
            for item in islice(self._files(root).iter_files(), 2_000)
        ]

    def _discover_dependencies(self, root: Path) -> list[PackageDependency]:
        reader = self._files(root)
        found: dict[str, PackageDependency] = {}

        def remember(item: PackageDependency) -> None:
            key = item.name.lower().replace("_", "-")
            current = found.get(key)
            if current is None or (item.version is not None and current.version is None):
                found[key] = item

        try:
            data = tomllib.loads(reader.read("pyproject.toml").content)
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
        except (tomllib.TOMLDecodeError, UnsafePathError):
            pass

        for name in reader.names():
            if "requirements" not in name or not name.endswith(".txt"):
                continue
            try:
                content = reader.read(name).content
            except UnsafePathError:
                continue
            for line in content.splitlines():
                match = REQUIREMENT_RE.match(line)
                if match and not line.lstrip().startswith(("#", "-")):
                    remember(
                        PackageDependency(
                            name=match.group(1),
                            version=match.group(2),
                            source_file=name,
                        )
                    )

        for lock_name in ("uv.lock", "poetry.lock"):
            try:
                data = tomllib.loads(reader.read(lock_name).content)
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
            except (tomllib.TOMLDecodeError, UnsafePathError):
                pass
        return sorted(found.values(), key=lambda item: item.name.lower())

    def _summarize_python(
        self,
        root: Path,
        files: list[FileEntry],
        dependencies: list[PackageDependency],
    ) -> str:
        reader = self._files(root)
        modules = 0
        imports: set[str] = set()
        functions = 0
        classes = 0
        for entry in files:
            if entry.language != "python":
                continue
            modules += 1
            try:
                tree = ast.parse(reader.read(entry.path).content)
            except (SyntaxError, UnsafePathError):
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
        reader = self._files(root)
        for relative in patch.changed_files:
            try:
                reader.read(relative)
            except UnsafePathError as exc:
                raise PatchRejectedError(f"unsafe patch target: {exc}") from exc
            if Path(relative).suffix not in {".py", ".toml", ".txt", ".lock"}:
                raise PatchRejectedError(f"unsupported patch target: {relative}")

    def _files(self, root: Path) -> RepositoryFiles:
        return RepositoryFiles(
            root, self._settings.max_file_bytes, workspace_root=self._workspace_root
        )

    def _assert_under_workspace(self, path: Path) -> None:
        if not path.is_relative_to(self._workspace_root):
            raise UnsafePathError("path escaped workspace root")

    @staticmethod
    def _safe_error(result: CommandResult, fallback: str) -> str:
        text = (result.stderr or result.stdout).strip().splitlines()
        return text[-1][:500] if text else fallback

    def _count_shell_true(self, root: Path) -> int:
        count = 0
        for item in self._files(root).iter_files():
            if Path(item.relative).suffix != ".py":
                continue
            try:
                tree = ast.parse(item.content)
            except SyntaxError:
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
