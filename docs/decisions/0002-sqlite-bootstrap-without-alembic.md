# ADR 0002: Self-initializing SQLite schema for the local MVP

Status: Accepted

The local single-user MVP creates its small `runs` and `events` tables with
idempotent SQL at startup. LangGraph owns its separate checkpoint schema.
Alembic is reserved for the first schema evolution or multi-user deployment;
introducing migration machinery before a first schema change would add moving
parts without improving recovery or compatibility.
