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

Models return search/replace edits (`EditProposal`), never a diff. The developer node
applies them to the full workspace files - not the possibly truncated prompt excerpt -
and renders the unified diff itself; an excerpt that is missing or not unique rejects the
proposal. The rendered diff then passes the same gates as a codemod's diff (ADR 0010).

Every patch attempt - an automatic repair or a reviewer-requested regeneration - starts
from the workspace's base revision: the previous attempt's recorded diff is reversed
first, and a patch is refused on a workspace that still carries changes. The stored diff
is therefore exactly one attempt, and the publisher refuses to commit unless the working
tree still equals that validated diff. Post-patch validation compares high/critical
findings with the originals by identity (source, rule, file, flagged line text) across
code scanners and OSV, so a patch cannot trade one high finding for another (ADR 0007).

Each run uses its UUID as the LangGraph `thread_id`. Application events have a
monotonic per-run sequence and are persisted separately from graph checkpoints,
allowing SSE clients to reconnect with `Last-Event-ID`.
