from pathlib import Path

import httpx
import respx

from orod.adapters.vector.chroma import ChromaAdvisoryStore


@respx.mock
async def test_chroma_persists_and_searches_advisory(tmp_path: Path) -> None:
    respx.post("http://ollama.local/api/embed").mock(
        return_value=httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3, 0.4]]})
    )
    store = ChromaAdvisoryStore(tmp_path / "chroma", "http://ollama.local", "embed-demo")

    cached = await store.upsert_advisory(
        {
            "id": "GHSA-demo",
            "summary": "Shell injection",
            "details": "Avoid shell execution for untrusted values.",
            "aliases": ["CVE-2099-0001"],
            "modified": "2099-01-01T00:00:00Z",
        }
    )
    results = await store.search("unsafe shell call", limit=1)

    assert cached is True
    assert results and "GHSA-demo" in results[0]
