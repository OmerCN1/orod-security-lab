from __future__ import annotations

import asyncio
from pathlib import Path

import aiosqlite

from orod.domain.events import RunEvent
from orod.domain.models import RunRecord


class SQLiteRunStore:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at REAL NOT NULL DEFAULT 0
                )
                """
            )
            await self._ensure_created_at_column(db)
            await db.execute(
                """
                CREATE TABLE IF NOT EXISTS events (
                    run_id TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (run_id, sequence)
                )
                """
            )
            await db.execute(
                "CREATE INDEX IF NOT EXISTS idx_events_run ON events(run_id, sequence)"
            )
            await db.execute("CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at DESC)")
            await db.commit()

    @staticmethod
    async def _ensure_created_at_column(db: aiosqlite.Connection) -> None:
        """Bootstrap-style migration for databases created before ordering was needed.

        ISO-8601 text cannot be ordered lexically here: a timestamp whose microsecond
        component is zero serialises as ``...15Z`` while others serialise as
        ``...15.001000Z``, and 'Z' sorts above '.', so the oldest run would surface first.
        The column stores a POSIX timestamp instead, which orders numerically.
        """
        cursor = await db.execute("PRAGMA table_info(runs)")
        columns = {str(row[1]) for row in await cursor.fetchall()}
        if "created_at" in columns:
            return
        await db.execute("ALTER TABLE runs ADD COLUMN created_at REAL NOT NULL DEFAULT 0")
        # julianday keeps sub-second precision; strftime('%s', ...) would collapse every
        # run created within the same second onto one value, and the id tiebreaker is a
        # random UUID rather than anything time-ordered.
        await db.execute(
            """
            UPDATE runs
            SET created_at = COALESCE(
                (julianday(json_extract(payload, '$.created_at')) - 2440587.5) * 86400.0,
                0
            )
            """
        )

    async def create_run(self, run: RunRecord) -> None:
        async with self._lock, aiosqlite.connect(self._path) as db:
            await db.execute(
                "INSERT INTO runs(id, payload, created_at) VALUES (?, ?, ?)",
                (run.id, run.model_dump_json(), run.created_at.timestamp()),
            )
            await db.commit()

    async def get_run(self, run_id: str) -> RunRecord | None:
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute("SELECT payload FROM runs WHERE id = ?", (run_id,))
            row = await cursor.fetchone()
        return RunRecord.model_validate_json(row[0]) if row else None

    async def list_runs(self, limit: int = 50, offset: int = 0) -> list[RunRecord]:
        """Most recent runs first, ordered by the numeric ``created_at`` column."""
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                """
                SELECT payload FROM runs
                ORDER BY created_at DESC, id DESC
                LIMIT ? OFFSET ?
                """,
                (max(1, min(limit, 200)), max(0, offset)),
            )
            rows = await cursor.fetchall()
        return [RunRecord.model_validate_json(row[0]) for row in rows]

    async def save_run(self, run: RunRecord) -> None:
        async with self._lock, aiosqlite.connect(self._path) as db:
            await db.execute(
                """
                INSERT INTO runs(id, payload, created_at) VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    payload = excluded.payload,
                    created_at = excluded.created_at
                """,
                (run.id, run.model_dump_json(), run.created_at.timestamp()),
            )
            await db.commit()

    async def append_event(self, event: RunEvent) -> RunEvent:
        async with self._lock, aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                "SELECT COALESCE(MAX(sequence), 0) + 1 FROM events WHERE run_id = ?",
                (event.run_id,),
            )
            row = await cursor.fetchone()
            if row is None:
                raise RuntimeError("failed to allocate event sequence")
            event.sequence = int(row[0])
            await db.execute(
                "INSERT INTO events(run_id, sequence, payload) VALUES (?, ?, ?)",
                (event.run_id, event.sequence, event.model_dump_json()),
            )
            await db.commit()
        return event

    async def list_events(self, run_id: str, after: int = 0) -> list[RunEvent]:
        async with aiosqlite.connect(self._path) as db:
            cursor = await db.execute(
                """
                SELECT payload FROM events
                WHERE run_id = ? AND sequence > ?
                ORDER BY sequence ASC
                """,
                (run_id, after),
            )
            rows = await cursor.fetchall()
        return [RunEvent.model_validate_json(row[0]) for row in rows]
