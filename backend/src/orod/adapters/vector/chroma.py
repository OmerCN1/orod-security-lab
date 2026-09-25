from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import chromadb
import httpx


class ChromaAdvisoryStore:
    def __init__(
        self,
        path: Path,
        ollama_base_url: str,
        embedding_model: str,
    ) -> None:
        self._path = path
        self._ollama_base_url = ollama_base_url.rstrip("/")
        self._embedding_model = embedding_model
        self._client: Any | None = None
        self._collection: Any | None = None

    def _get_collection(self) -> Any:
        if self._collection is None:
            self._path.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(self._path))
            self._collection = self._client.get_or_create_collection(
                "osv_advisories",
                metadata={"hnsw:space": "cosine"},
            )
        return self._collection

    async def _embed(self, text: str) -> list[float]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                f"{self._ollama_base_url}/api/embed",
                json={"model": self._embedding_model, "input": text},
            )
            response.raise_for_status()
            payload = response.json()
        embeddings = payload.get("embeddings") or []
        if not embeddings:
            raise RuntimeError("Ollama returned no embedding")
        return [float(value) for value in embeddings[0]]

    async def upsert_advisory(self, advisory: dict[str, object]) -> bool:
        advisory_id = str(advisory.get("id") or "")
        if not advisory_id:
            return False
        text = "\n".join(
            part
            for part in (
                advisory_id,
                str(advisory.get("summary") or ""),
                str(advisory.get("details") or ""),
            )
            if part
        )[:20_000]
        embedding = await self._embed(text)
        raw_aliases = advisory.get("aliases")
        aliases = raw_aliases if isinstance(raw_aliases, list) else []
        modified = str(advisory.get("modified") or "")
        metadata = {
            "advisory_id": advisory_id,
            "aliases": ",".join(str(alias) for alias in aliases),
            "modified": modified,
        }
        collection = await asyncio.to_thread(self._get_collection)
        await asyncio.to_thread(
            collection.upsert,
            ids=[advisory_id],
            documents=[text],
            embeddings=[embedding],
            metadatas=[metadata],
        )
        return True

    async def search(self, query: str, limit: int = 3) -> list[str]:
        embedding = await self._embed(query[:10_000])
        collection = await asyncio.to_thread(self._get_collection)
        result = await asyncio.to_thread(
            collection.query,
            query_embeddings=[embedding],
            n_results=max(1, min(limit, 10)),
        )
        documents = result.get("documents") or [[]]
        return [str(value) for value in documents[0]]
