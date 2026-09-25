# Architecture

OROD is a ports-and-adapters application. FastAPI starts application use cases;
the use cases invoke a LangGraph team; graph nodes use protocols; concrete
GitHub, Ollama, scanner, Chroma, SQLite, and command adapters live at the edge.

```text
React --REST/SSE--> FastAPI --> RunCoordinator --> LangGraph Team
                                         |              |
                                         v              v
                                  SQLite event log   Agent ports
                                                        |
                    GitHub CLI / Bandit / OSV / Chroma / Ollama
```

OSV package/version matching is authoritative. Vector similarity is used only
to select compact advisory context for explanations and remediation prompts.

Each run uses its UUID as the LangGraph `thread_id`. Application events have a
monotonic per-run sequence and are persisted separately from graph checkpoints,
allowing SSE clients to reconnect with `Last-Event-ID`.
