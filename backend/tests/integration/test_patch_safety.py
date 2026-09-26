from pathlib import Path

import pytest

from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.adapters.repository.git import GitRepositoryAdapter
from orod.config import Settings
from orod.domain.errors import PatchRejectedError, WorkspaceIntegrityError
from orod.domain.models import PatchProposal, RepositorySnapshot


def edit(path: str, before: str = "value = 1", after: str = "value = 2") -> str:
    return f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-{before}\n+{after}\n"


@pytest.fixture
async def repository(tmp_path: Path) -> tuple[GitRepositoryAdapter, RepositorySnapshot, Path]:
    root = tmp_path / "repo"
    root.mkdir()
    for name in ("app.py", "other.py", ".env", ".env.production", "bad.bin"):
        (root / name).write_text("value = 1\n")
    runner = SafeCommandRunner({"git"}, tmp_path)
    for argv in (
        ["git", "init", "-b", "main"],
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "baseline",
        ],
    ):
        assert (await runner.run(argv, root)).return_code == 0
    adapter = GitRepositoryAdapter(Settings(workspace_root=tmp_path), runner)
    snapshot = RepositorySnapshot(repository_url="demo://test", workspace_path=str(root))
    return adapter, snapshot, root


async def commit_baseline(root: Path) -> None:
    """Record test setup as the base revision; patches must start from a clean base."""
    runner = SafeCommandRunner({"git"}, root.parent)
    for argv in (
        ["git", "add", "."],
        [
            "git",
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.invalid",
            "commit",
            "-m",
            "setup",
        ],
    ):
        assert (await runner.run(argv, root)).return_code == 0


def proposal(diff: str, paths: list[str]) -> PatchProposal:
    return PatchProposal(unified_diff=diff, changed_files=paths, finding_ids=[], explanation="Test")


async def test_applies_all_declared_files(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
) -> None:
    adapter, snapshot, root = repository
    result = await adapter.apply_patch(
        snapshot, proposal(edit("app.py") + edit("other.py"), ["other.py", "app.py"])
    )
    assert "app.py" in result and "other.py" in result
    assert (root / "app.py").read_text() == (root / "other.py").read_text() == "value = 2\n"


@pytest.mark.parametrize("extra", ["other.py", ".env", ".env.production", "bad.bin"])
async def test_undeclared_target_rejected_before_any_write(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
    extra: str,
) -> None:
    adapter, snapshot, root = repository
    with pytest.raises(PatchRejectedError, match="do not match"):
        await adapter.apply_patch(snapshot, proposal(edit("app.py") + edit(extra), ["app.py"]))
    assert (root / "app.py").read_text() == (root / extra).read_text() == "value = 1\n"


@pytest.mark.parametrize("path", [".env", ".env.production", "bad.bin"])
async def test_declared_forbidden_target_rejected(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
    path: str,
) -> None:
    adapter, snapshot, _ = repository
    with pytest.raises(PatchRejectedError):
        await adapter.apply_patch(snapshot, proposal(edit(path), [path]))


@pytest.mark.parametrize("parent_link", [False, True])
async def test_symlink_and_symlink_parent_rejected(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
    parent_link: bool,
) -> None:
    adapter, snapshot, root = repository
    alias = root / ("alias" if parent_link else "alias.py")
    alias.symlink_to(root if parent_link else root / "app.py", target_is_directory=parent_link)
    name = "alias/app.py" if parent_link else "alias.py"
    with pytest.raises(PatchRejectedError, match="unsafe patch target"):
        await adapter.apply_patch(snapshot, proposal(edit(name), [name]))
    assert (root / "app.py").read_text() == "value = 1\n"


@pytest.mark.parametrize("content", [b"\x00value = 1\n", b"\xffvalue = 1\n"])
async def test_binary_file_rejected(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
    content: bytes,
) -> None:
    adapter, snapshot, root = repository
    (root / "app.py").write_bytes(content)
    with pytest.raises(PatchRejectedError):
        await adapter.apply_patch(snapshot, proposal(edit("app.py"), ["app.py"]))
    assert (root / "app.py").read_bytes() == content


@pytest.mark.parametrize(
    "diff,paths",
    [
        (edit("app.py"), ["app.py", "other.py"]),
        (edit("app.py"), ["app.py", "app.py"]),
        (edit("app.py") + edit("app.py"), ["app.py"]),
        (edit("../outside.py"), ["../outside.py"]),
        (edit("/absolute.py"), ["/absolute.py"]),
        (edit("./app.py"), ["./app.py"]),
        (edit("app.py").replace("+++ b/app.py", "+++ b/other.py"), ["app.py"]),
        ("diff --git a/other.py b/other.py\n" + edit("app.py"), ["app.py"]),
        (
            "diff --git a/app.py b/app.py\nold mode 100644\nnew mode 100755\n" + edit("app.py"),
            ["app.py"],
        ),
        ("diff --git a/app.py b/app.py\nGIT binary patch\nliteral 0\n", ["app.py"]),
        (edit("app.py").replace("--- a/app.py", "--- /dev/null"), ["app.py"]),
        (edit("app.py").replace("@@ -1 +1 @@", "@@ -1,2 +1,2 @@"), ["app.py"]),
        (edit("app.py") + "unparsed trailing text\n", ["app.py"]),
    ],
)
async def test_rejects_ambiguous_or_unsupported_patch(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
    diff: str,
    paths: list[str],
) -> None:
    adapter, snapshot, root = repository
    with pytest.raises(PatchRejectedError):
        await adapter.apply_patch(snapshot, proposal(diff, paths))
    assert (root / "app.py").read_text() == "value = 1\n"


async def test_header_like_source_lines_are_hunk_data(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
) -> None:
    adapter, snapshot, root = repository
    (root / "app.py").write_text("-- a/.env\n")
    await commit_baseline(root)
    await adapter.apply_patch(
        snapshot, proposal(edit("app.py", "-- a/.env", "++ b/.env"), ["app.py"])
    )
    assert (root / ".env").read_text() == "value = 1\n"


async def test_normal_git_headers_and_missing_final_source_newline(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
) -> None:
    adapter, snapshot, root = repository
    (root / "app.py").write_text("value = 1")
    await commit_baseline(root)
    diff = (
        "diff --git a/app.py b/app.py\nindex 1234567..abcdef0 100644\n"
        "--- a/app.py\n+++ b/app.py\n@@ -1 +1 @@\n-value = 1\n"
        "\\ No newline at end of file\n+value = 2\n\\ No newline at end of file\n"
    )
    await adapter.apply_patch(snapshot, proposal(diff, ["app.py"]))
    assert (root / "app.py").read_text() == "value = 2"


@pytest.mark.parametrize("limit", ["lines", "bytes", "file"])
async def test_rejects_oversized_patch_or_target(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
    limit: str,
) -> None:
    adapter, snapshot, root = repository
    if limit == "lines":
        adapter._settings.max_diff_lines = 1
    elif limit == "bytes":
        adapter._settings.max_file_bytes = 10
    else:
        adapter._settings.max_file_bytes = 100
        (root / "app.py").write_text("value = 1\n" + "#" * 101)
    with pytest.raises(PatchRejectedError, match="limit"):
        await adapter.apply_patch(snapshot, proposal(edit("app.py"), ["app.py"]))
    assert (root / "app.py").read_text().startswith("value = 1")


async def test_a_second_attempt_starts_from_the_base_revision(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
) -> None:
    adapter, snapshot, root = repository
    first = await adapter.apply_patch(snapshot, proposal(edit("app.py"), ["app.py"]))
    await adapter.revert_patch(snapshot, first)
    assert (root / "app.py").read_text() == "value = 1\n"

    second = await adapter.apply_patch(snapshot, proposal(edit("other.py"), ["other.py"]))
    # The stored diff is this attempt alone, so it matches what would be published.
    assert "other.py" in second and "app.py" not in second


async def test_a_patch_cannot_stack_on_an_earlier_one(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
) -> None:
    adapter, snapshot, root = repository
    await adapter.apply_patch(snapshot, proposal(edit("app.py"), ["app.py"]))
    with pytest.raises(WorkspaceIntegrityError, match="already carries changes"):
        await adapter.apply_patch(snapshot, proposal(edit("other.py"), ["other.py"]))
    assert (root / "other.py").read_text() == "value = 1\n"


async def test_revert_is_a_no_op_on_a_clean_workspace(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
) -> None:
    adapter, snapshot, root = repository
    applied = await adapter.apply_patch(snapshot, proposal(edit("app.py"), ["app.py"]))
    await adapter.revert_patch(snapshot, applied)
    # A re-executed node reverts again; the workspace is already at its base.
    await adapter.revert_patch(snapshot, applied)
    assert (root / "app.py").read_text() == "value = 1\n"


async def test_revert_refuses_a_workspace_that_changed_after_the_patch(
    repository: tuple[GitRepositoryAdapter, RepositorySnapshot, Path],
) -> None:
    adapter, snapshot, root = repository
    applied = await adapter.apply_patch(snapshot, proposal(edit("app.py"), ["app.py"]))
    (root / "other.py").write_text("value = 3\n")
    with pytest.raises(WorkspaceIntegrityError, match="changed after the patch"):
        await adapter.revert_patch(snapshot, applied)
    assert (root / "app.py").read_text() == "value = 2\n"
