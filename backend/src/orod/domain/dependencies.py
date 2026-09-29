"""Deterministic dependency remediation: which version to pin, and where to pin it.

OSV is authoritative for whether a package version is affected, so the target version
comes from the advisories' own ranges, never from a model. The post-patch OSV rescan
checks the chosen version again; this module only has to choose well.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import PurePosixPath

from packaging.version import InvalidVersion, Version

from orod.domain.models import DependencyUpgrade, Finding, FindingSource

PYPROJECT = "pyproject.toml"

# The version group matches the one dependency discovery uses, so a pin is rewritten
# only when its text is exactly the version OSV was asked about.
_REQUIREMENT_PIN = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*==\s*([^\s;]+)")
_PYPROJECT_PIN = re.compile(r"""(["'])\s*([A-Za-z0-9_.-]+)\s*==\s*([^\s;"']+)""")


def normalize_name(name: str) -> str:
    """PEP 503 normalisation: ``PyYAML``, ``pyyaml`` and ``py_yaml`` differ only in spelling."""
    return re.sub(r"[-_.]+", "-", name).lower()


def is_requirements_file(name: str) -> bool:
    return "requirements" in name and name.endswith(".txt")


def is_editable_manifest(path: str | None) -> bool:
    """Manifests whose exact pins can be edited. Lockfiles are generated, never edited."""
    if path is None or PurePosixPath(path).name != path:
        return False
    return path == PYPROJECT or is_requirements_file(path)


def is_remediable(finding: Finding) -> bool:
    """An OSV finding a pin change can resolve: a fix above the pinned version exists."""
    dependency = finding.dependency
    if (
        finding.source != FindingSource.OSV
        or dependency is None
        or dependency.version is None
        or not is_editable_manifest(dependency.source_file)
    ):
        return False
    return _smallest_fix_above(dependency.version, finding.fixed_versions) is not None


def plan_upgrades(findings: Iterable[Finding]) -> list[DependencyUpgrade]:
    """One upgrade per pinned package, to a version that clears all of its advisories.

    Each advisory is cleared by its smallest fixed version above the pin: the range that
    contains the pin ends there. The package moves to the highest of those, the smallest
    version that clears every advisory at once. Findings that no pin change resolves are
    left out, and the residual check reports them.
    """
    groups: dict[tuple[str, str], list[Finding]] = {}
    for finding in findings:
        if not is_remediable(finding):
            continue
        dependency = finding.dependency
        assert dependency is not None and dependency.version is not None
        groups.setdefault((normalize_name(dependency.name), dependency.version), []).append(finding)
    upgrades: list[DependencyUpgrade] = []
    for (_, current), items in sorted(groups.items()):
        fixes = [_smallest_fix_above(current, item.fixed_versions) for item in items]
        target = max((fix for fix in fixes if fix is not None), key=lambda pair: pair[0])
        dependency = items[0].dependency
        assert dependency is not None
        upgrades.append(
            DependencyUpgrade(
                name=dependency.name,
                current_version=current,
                target_version=target[1],
                advisory_ids=sorted({item.rule_id for item in items}),
                finding_ids=[item.id for item in items],
            )
        )
    return upgrades


def rewrite_requirements(content: str, upgrades: Iterable[DependencyUpgrade]) -> str:
    """Move every exact pin of an upgraded package in a requirements file."""
    wanted = _wanted(upgrades)
    lines = content.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.lstrip().startswith(("#", "-")):
            continue
        match = _REQUIREMENT_PIN.match(line)
        if match is None:
            continue
        target = wanted.get((normalize_name(match[1]), match[2]))
        if target is not None:
            lines[index] = line[: match.start(2)] + target + line[match.end(2) :]
    return "".join(lines)


def rewrite_pyproject(content: str, upgrades: Iterable[DependencyUpgrade]) -> str:
    """Move every quoted exact pin of an upgraded package in ``pyproject.toml``."""
    wanted = _wanted(upgrades)

    def replace(match: re.Match[str]) -> str:
        target = wanted.get((normalize_name(match[2]), match[3]))
        if target is None:
            return match[0]
        return match[0][: match.start(3) - match.start(0)] + target

    return _PYPROJECT_PIN.sub(replace, content)


def _wanted(upgrades: Iterable[DependencyUpgrade]) -> dict[tuple[str, str], str]:
    return {
        (normalize_name(item.name), item.current_version): item.target_version for item in upgrades
    }


def _smallest_fix_above(current: str, fixed_versions: Iterable[str]) -> tuple[Version, str] | None:
    try:
        pinned = Version(current)
    except InvalidVersion:
        return None
    candidates: list[tuple[Version, str]] = []
    for raw in fixed_versions:
        try:
            version = Version(raw)
        except InvalidVersion:
            continue
        if version > pinned:
            candidates.append((version, raw))
    return min(candidates, key=lambda pair: pair[0]) if candidates else None
