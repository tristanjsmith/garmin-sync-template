"""Database access for garmin-sync (psycopg 3).

Connects as the limited garmin_sync role via DATABASE_URL, always with
sslmode=require. Upserts only touch a row when its payload (or date) actually
changed, so re-fetching unchanged data costs no writes.
"""

from __future__ import annotations

import os
from datetime import date

import psycopg
from psycopg.types.json import Jsonb

UPSERT_BATCH_SIZE = 500

_UPSERT_SQL = """
insert into garmin.raw_records as r (data_type, source_id, calendar_date, payload, fetched_at)
select %(data_type)s, t.source_id, t.calendar_date, t.payload, now()
from unnest(%(source_ids)s::text[], %(dates)s::date[], %(payloads)s::jsonb[])
    as t(source_id, calendar_date, payload)
on conflict (data_type, source_id) do update
    set calendar_date = excluded.calendar_date,
        payload       = excluded.payload,
        fetched_at    = excluded.fetched_at
    where r.payload is distinct from excluded.payload
       or r.calendar_date is distinct from excluded.calendar_date
returning (xmax = 0) as inserted
"""


def connect() -> psycopg.Connection:
    url = os.environ.get("DATABASE_URL", "").strip()
    if not url:
        raise RuntimeError("DATABASE_URL is not set")
    # sslmode passed as a keyword overrides anything in the URL.
    return psycopg.connect(
        url,
        sslmode="require",
        connect_timeout=30,
        application_name="garmin-sync",
        autocommit=True,  # transactions are opened explicitly per data type
    )


def start_run(conn: psycopg.Connection, mode: str, date_from: date, date_to: date) -> int:
    with conn.transaction():
        row = conn.execute(
            "insert into garmin.sync_runs (status, mode, date_from, date_to, counts) "
            "values ('running', %s, %s, %s, '{}'::jsonb) returning id",
            (mode, date_from, date_to),
        ).fetchone()
    return int(row[0])


def finish_run(
    conn: psycopg.Connection, run_id: int, status: str, counts: dict, error: str | None
) -> None:
    with conn.transaction():
        conn.execute(
            "update garmin.sync_runs set finished_at = now(), status = %s, counts = %s, error = %s "
            "where id = %s",
            (status, Jsonb(counts), error, run_id),
        )


def upsert_records(
    conn: psycopg.Connection,
    data_type: str,
    records: list[tuple[str, date | None, object]],
) -> dict[str, int]:
    """Upsert (source_id, calendar_date, payload) records for one data type in a
    single transaction. Returns {fetched, inserted, updated, unchanged}."""
    counts = {"fetched": len(records), "inserted": 0, "updated": 0, "unchanged": 0}
    with conn.transaction():
        for i in range(0, len(records), UPSERT_BATCH_SIZE):
            batch = records[i : i + UPSERT_BATCH_SIZE]
            rows = conn.execute(
                _UPSERT_SQL,
                {
                    "data_type": data_type,
                    "source_ids": [r[0] for r in batch],
                    "dates": [r[1] for r in batch],
                    "payloads": [Jsonb(r[2]) for r in batch],
                },
            ).fetchall()
            inserted = sum(1 for (was_insert,) in rows if was_insert)
            counts["inserted"] += inserted
            counts["updated"] += len(rows) - inserted
            counts["unchanged"] += len(batch) - len(rows)
    return counts
