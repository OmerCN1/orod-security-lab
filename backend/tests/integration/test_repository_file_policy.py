import os
from pathlib import Path

import pytest

from orod.adapters.execution.container import ContainerCommandRunner
from orod.adapters.execution.subprocess import SafeCommandRunner
from orod.adapters.repository.files import RepositoryFiles
from orod.adapters.repository.git import GitRepositoryAdapter
from orod.adapters.scanners.builtin import BuiltinPythonScanner
from orod.config import Settings
from orod.domain.errors import PatchRejectedError, UnsafePathError
from orod.domain.models import FileEntry, PatchProposal, RepositorySnapshot


def patch(path: str) -> PatchProposal:
    return PatchProposal(
        unified_diff=f"--- a/{path}\n+++ b/{path}\n@@ -1 +1 @@\n-x = 1\n+x = 2\n",
        changed_files=[path],
        finding_ids=[],
        explanation="Test policy",
    )


@pytest.mark.parametrize(
    "kind",
    [
        "internal_link",
        "external_link",
        "broken_link",
        "parent_link",
        "directory",
        "fifo",
        "binary",
        "invalid_utf8",
        "control_bytes",
        "oversized",
        "hidden",
        "secret",
        "ignored",
    ],
)
async def test_inventory_reads_patch_and_container_share_policy(tmp_path: Path, kind: str) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    settings = Settings(workspace_root=tmp_path, max_file_bytes=256)
    adapter = GitRepositoryAdapter(settings, SafeCommandRunner({"git"}, tmp_path))
    name = "unsafe.py"
    target = root / name
    outside = tmp_path / "outside.py"
    outside.write_text("x = 1\n")
    if kind == "internal_link":
        (root / "good.py").write_text("x = 1\n")
        target.symlink_to(root / "good.py")
    elif kind == "external_link":
        target.symlink_to(outside)
    elif kind == "broken_link":
        target.symlink_to(root / "missing.py")
    elif kind == "parent_link":
        target.symlink_to(tmp_path, target_is_directory=True)
        name = "unsafe.py/outside.py"
    elif kind == "directory":
        target.mkdir()
    elif kind == "fifo":
        os.mkfifo(target)
    elif kind == "binary":
        target.write_bytes(b"x = 1\n\x00")
    elif kind == "invalid_utf8":
        target.write_bytes(b"x = 1\n\xff")
    elif kind == "control_bytes":
        target.write_bytes(b"x = 1\n\x01")
    elif kind == "oversized":
        target.write_text("x = 1\n" + "#" * 257)
    else:
        name = {"hidden": ".env.production", "secret": "id_rsa", "ignored": "venv/app.py"}[kind]
        target = root / name
        target.parent.mkdir(exist_ok=True)
        target.write_text("x = 1\n")
    snapshot = RepositorySnapshot(repository_url="demo://test", workspace_path=str(root))

    assert name not in {entry.path for entry in adapter._inventory_files(root)}
    with pytest.raises(UnsafePathError):
        await adapter.read_files(snapshot, [name])
    with pytest.raises(UnsafePathError):
        await adapter.read_base_files(snapshot, [name])
    with pytest.raises(PatchRejectedError):
        await adapter.apply_patch(snapshot, patch(name))
    destination = tmp_path / "copy"
    destination.mkdir()
    ContainerCommandRunner(settings)._copy_input(root, destination)
    assert not (destination / name).exists()
    assert outside.read_text() == "x = 1\n"


@pytest.mark.parametrize(
    "manifest,content",
    [
        ("requirements.txt", "outside-package==9.9\n"),
        ("dev-requirements.txt", "outside-package==9.9\n"),
        ("pyproject.toml", '[project]\ndependencies = ["outside-package==9.9"]\n'),
        ("uv.lock", '[[package]]\nname = "outside-package"\nversion = "9.9"\n'),
        ("poetry.lock", '[[package]]\nname = "outside-package"\nversion = "9.9"\n'),
    ],
)
@pytest.mark.parametrize("kind", ["external_link", "internal_link", "oversized", "binary", "fifo"])
def test_dependency_discovery_never_reads_unsafe_manifests(
    tmp_path: Path,
    manifest: str,
    content: str,
    kind: str,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    adapter = GitRepositoryAdapter(
        Settings(workspace_root=tmp_path, max_file_bytes=128), SafeCommandRunner({"git"}, tmp_path)
    )
    path = root / manifest
    if kind.endswith("link"):
        target = (root if kind == "internal_link" else tmp_path) / "input.data"
        target.write_text(content)
        path.symlink_to(target)
    elif kind == "oversized":
        path.write_text(content + "#" * 129)
    elif kind == "binary":
        path.write_bytes(content.encode() + b"\x00\xff")
    else:
        os.mkfifo(path)
    assert adapter._discover_dependencies(root) == []


def test_safe_manifests_still_share_version_precedence_and_byte_boundary(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "pyproject.toml").write_text('[project]\ndependencies = ["httpx>=0.27"]\n')
    (root / "requirements.txt").write_text("requests==2.32.0\n")
    content = '[[package]]\nname = "httpx"\nversion = "0.28.1"\n'
    (root / "uv.lock").write_text(content)
    (root / ".env.requirements.txt").write_text("hidden-package==1.0\n")
    limit = len(content.encode())
    adapter = GitRepositoryAdapter(
        Settings(workspace_root=tmp_path, max_file_bytes=limit),
        SafeCommandRunner({"git"}, tmp_path),
    )
    dependencies = adapter._discover_dependencies(root)
    assert [(item.name, item.version) for item in dependencies] == [
        ("httpx", "0.28.1"),
        ("requests", "2.32.0"),
    ]
    reader = RepositoryFiles(root, limit, workspace_root=tmp_path)
    assert reader.read("uv.lock").size == limit


@pytest.mark.parametrize(
    "relative", ["../outside.py", "/etc/passwd", "./app.py", "dir//app.py", ""]
)
def test_rejects_noncanonical_paths(tmp_path: Path, relative: str) -> None:
    with pytest.raises(UnsafePathError):
        RepositoryFiles(tmp_path, 128).read(relative)


@pytest.mark.parametrize("parent", [False, True])
def test_open_rejects_symlink_swapped_in_after_checks(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    parent: bool,
) -> None:
    root = tmp_path / "repo"
    (root / "package").mkdir(parents=True)
    (root / "package" / "app.py").write_text("x = 1\n")
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "app.py").write_text("outside_data = 1\n")
    original_open = os.open
    swapped = False

    def swap_before_open(
        path: str | Path, flags: int, mode: int = 0o777, *, dir_fd: int | None = None
    ) -> int:
        nonlocal swapped
        if not swapped and path == ("package" if parent else "app.py"):
            swapped = True
            if parent:
                (root / "package").rename(root / "old-package")
                (root / "package").symlink_to(outside, target_is_directory=True)
            else:
                (root / "package" / "app.py").unlink()
                (root / "package" / "app.py").symlink_to(outside / "app.py")
        return original_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", swap_before_open)
    with pytest.raises(UnsafePathError):
        RepositoryFiles(root, 128, workspace_root=tmp_path).read("package/app.py")
    assert swapped


async def test_changed_inventory_entry_cannot_bypass_summary_or_builtin_scan(
    tmp_path: Path,
) -> None:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "app.py").write_text("x = 1\n")
    adapter = GitRepositoryAdapter(
        Settings(workspace_root=tmp_path), SafeCommandRunner({"git"}, tmp_path)
    )
    inventory = adapter._inventory_files(root)
    outside = tmp_path / "external.py"
    outside.write_text("import outside_only_module\neval(input())\n")
    (root / "app.py").unlink()
    (root / "app.py").symlink_to(outside)
    assert "outside_only_module" not in adapter._summarize_python(root, inventory, [])
    snapshot = RepositorySnapshot(
        repository_url="demo://test", workspace_path=str(root), files=inventory
    )
    assert await BuiltinPythonScanner(workspace_root=tmp_path).scan(snapshot) == []
    snapshot.files = [FileEntry(path="../external.py", size=1, language="python")]
    assert await BuiltinPythonScanner(workspace_root=tmp_path).scan(snapshot) == []


def test_symlink_repository_root_is_not_resolved_before_checking(tmp_path: Path) -> None:
    real = tmp_path / "real"
    real.mkdir()
    (real / "app.py").write_text("x = 1\n")
    alias = tmp_path / "alias"
    alias.symlink_to(real, target_is_directory=True)
    with pytest.raises(UnsafePathError):
        RepositoryFiles(alias, 128, workspace_root=tmp_path).read("app.py")


async def test_fixture_copy_does_not_dereference_manifest_symlink(tmp_path: Path) -> None:
    fixture = tmp_path / "fixtures" / "sample"
    fixture.mkdir(parents=True)
    (fixture / "app.py").write_text("x = 1\n")
    outside = tmp_path / "outside.txt"
    outside.write_text("outside-package==9.9\n")
    (fixture / "requirements.txt").symlink_to(outside)
    workspace = tmp_path / "workspaces"
    workspace.mkdir()
    adapter = GitRepositoryAdapter(
        Settings(workspace_root=workspace, fixture_root=fixture.parent),
        SafeCommandRunner({"git"}, workspace),
    )
    snapshot = await adapter.prepare("demo://sample", None, "run", False)
    assert snapshot.dependencies == []
    assert [item.path for item in snapshot.files] == ["app.py"]
    assert (workspace / "run" / "requirements.txt").is_symlink()


def test_growth_after_stat_cannot_escape_the_read_budget(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    (tmp_path / "app.py").write_text("x" * 1000)
    real_fstat = os.fstat

    def report_stale_size(descriptor: int) -> os.stat_result:
        values = list(real_fstat(descriptor))
        values[6] = 1
        return os.stat_result(values)

    monkeypatch.setattr(os, "fstat", report_stale_size)
    with pytest.raises(UnsafePathError, match="byte limit"):
        RepositoryFiles(tmp_path, 128).read("app.py")


def test_limit_is_bytes_and_preserves_utf8_and_line_endings(tmp_path: Path) -> None:
    original = "é\r\n"
    (tmp_path / "app.py").write_bytes(original.encode())
    item = RepositoryFiles(tmp_path, 4).read("app.py")
    assert item.content == original
    assert item.size == 4
    with pytest.raises(UnsafePathError, match="byte limit"):
        RepositoryFiles(tmp_path, 3).read("app.py")
