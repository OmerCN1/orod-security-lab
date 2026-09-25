# ADR 0001: Local-first ports and adapters

Status: Accepted

OROD keeps domain and graph contracts independent of Ollama, Chroma, GitHub,
and FastAPI. Concrete services implement protocols. This preserves local-only
operation now and allows future e-commerce or game-analysis teams to reuse the
same orchestration and API shell.
