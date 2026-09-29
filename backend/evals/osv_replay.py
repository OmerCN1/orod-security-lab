"""Recorded OSV responses, replayed through the real OSV adapter.

A case that pins dependencies ships an ``osv.json`` next to its ``repo/``: the advisory
ids OSV returned for each pinned ``name==version`` and the advisories themselves, as
recorded from the live service by ``python -m evals record-osv``. The harness serves
them through an ``httpx`` transport, so the adapter's own parsing runs and the suite
never touches the network. A query the recording does not cover fails like an OSV
outage - the lookup is incomplete - instead of passing as "no advisories".
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
from pydantic import BaseModel, Field

from evals.manifest import CASES_ROOT, EvalCase
from orod.domain.dependencies import normalize_name

RECORDING_NAME = "osv.json"
OSV_API_ROOT = "https://api.osv.dev/v1"


class OSVRecording(BaseModel):
    recorded_at: str = ""
    # "pyyaml==5.3.1" -> advisory ids, in the order OSV returned them.
    queries: dict[str, list[str]] = Field(default_factory=dict)
    vulns: dict[str, dict[str, Any]] = Field(default_factory=dict)


def pin_key(name: str, version: str) -> str:
    return f"{normalize_name(name)}=={version}"


def load_recordings(cases: Iterable[EvalCase], root: Path = CASES_ROOT) -> OSVRecording:
    """Merge every selected case's recording; a pin recorded twice must agree."""
    merged = OSVRecording()
    for case in cases:
        path = root / case.id / RECORDING_NAME
        if not path.is_file():
            continue
        recording = OSVRecording.model_validate(json.loads(path.read_text(encoding="utf-8")))
        for key, ids in recording.queries.items():
            if merged.queries.setdefault(key, ids) != ids:
                raise ValueError(f"{case.id}: recording for {key} disagrees with another case")
        merged.vulns.update(recording.vulns)
    return merged


def replay_transport(recording: OSVRecording) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if request.method == "POST" and path == "/v1/querybatch":
            results: list[dict[str, Any]] = []
            for query in json.loads(request.content).get("queries", []):
                key = pin_key(str(query["package"]["name"]), str(query["version"]))
                if key not in recording.queries:
                    return httpx.Response(503, json={"error": f"{key} was not recorded"})
                ids = recording.queries[key]
                results.append({"vulns": [{"id": item} for item in ids]} if ids else {})
            return httpx.Response(200, json={"results": results})
        if request.method == "GET" and path.startswith("/v1/vulns/"):
            advisory = recording.vulns.get(path.removeprefix("/v1/vulns/"))
            if advisory is not None:
                return httpx.Response(200, json=advisory)
        return httpx.Response(404, json={"error": "not recorded"})

    return httpx.MockTransport(handle)


async def record(case_id: str, pins: list[str], root: Path = CASES_ROOT) -> Path:
    """Query live OSV for ``name==version`` pins and write the case's recording."""
    parsed: list[tuple[str, str]] = []
    for pin in pins:
        name, separator, version = pin.partition("==")
        if not separator or not name or not version:
            raise ValueError(f"expected name==version, got {pin!r}")
        parsed.append((name, version))
    recording = OSVRecording(recorded_at=datetime.now(UTC).isoformat(timespec="seconds"))
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(
            f"{OSV_API_ROOT}/querybatch",
            json={
                "queries": [
                    {"version": version, "package": {"ecosystem": "PyPI", "name": name}}
                    for name, version in parsed
                ]
            },
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        if len(results) != len(parsed):
            raise RuntimeError("OSV returned a result count that does not match the query")
        for (name, version), result in zip(parsed, results, strict=True):
            ids = [str(item["id"]) for item in result.get("vulns", [])]
            recording.queries[pin_key(name, version)] = ids
            for advisory_id in ids:
                if advisory_id not in recording.vulns:
                    detail = await client.get(f"{OSV_API_ROOT}/vulns/{advisory_id}")
                    detail.raise_for_status()
                    recording.vulns[advisory_id] = detail.json()
    path = root / case_id / RECORDING_NAME
    path.write_text(recording.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return path
