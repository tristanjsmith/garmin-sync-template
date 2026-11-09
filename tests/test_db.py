"""Tests for the database SQL and the database rules.

These tests need a test Postgres database. Set TEST_DATABASE_URL to the URL of
a database superuser. Example:
    TEST_DATABASE_URL=postgresql://postgres:postgres@localhost:5432/postgres
If TEST_DATABASE_URL is not set, the tests are skipped.

WARNING: These tests delete all rows in the garmin tables.
Use a test database only. Do not use your Supabase database.
"""

from __future__ import annotations

import os
import unittest
from datetime import date

from helpers import ROOT

TEST_URL = os.environ.get("TEST_DATABASE_URL", "").strip()
SYNC_PASSWORD = "testpassword123"

if TEST_URL:
    import psycopg
    from psycopg.conninfo import conninfo_to_dict

    import db


@unittest.skipUnless(TEST_URL, "TEST_DATABASE_URL is not set")
class DatabaseTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.admin = psycopg.connect(TEST_URL, autocommit=True)
        if "supabase" in (cls.admin.info.host or ""):
            raise RuntimeError("TEST_DATABASE_URL must not point to Supabase")
        for role in ("anon", "authenticated"):  # Supabase has these roles
            exists = cls.admin.execute("select 1 from pg_roles where rolname = %s", (role,)).fetchone()
            if not exists:
                cls.admin.execute(f"create role {role}")
        migration = (ROOT / "supabase" / "migrations" / "001_init.sql").read_text()
        cls.admin.execute(migration)
        cls.admin.execute(migration)  # the migration must be safe to run two times
        cls.admin.execute(f"alter role garmin_sync with password '{SYNC_PASSWORD}'")
        params = conninfo_to_dict(TEST_URL)
        params.update(user="garmin_sync", password=SYNC_PASSWORD)
        cls.conn = psycopg.connect(**params, autocommit=True)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.conn.close()
        cls.admin.close()

    def setUp(self) -> None:
        self.admin.execute("truncate garmin.raw_records, garmin.sync_runs restart identity")

    def test_insert_then_unchanged_then_updated(self) -> None:
        day = date(2026, 11, 8)
        records = [(day.isoformat(), day, {"value": 1}), ("other", day, {"value": 2})]
        first = db.upsert_records(self.conn, "sleep", records)
        self.assertEqual(first, {"fetched": 2, "inserted": 2, "updated": 0, "unchanged": 0})
        second = db.upsert_records(self.conn, "sleep", records)
        self.assertEqual(second, {"fetched": 2, "inserted": 0, "updated": 0, "unchanged": 2})
        changed = [(day.isoformat(), day, {"value": 3}), records[1]]
        third = db.upsert_records(self.conn, "sleep", changed)
        self.assertEqual(third, {"fetched": 2, "inserted": 0, "updated": 1, "unchanged": 1})
        count = self.admin.execute("select count(*) from garmin.raw_records").fetchone()[0]
        self.assertEqual(count, 2)

    def test_sync_runs_start_and_finish(self) -> None:
        run_id = db.start_run(self.conn, "manual", date(2026, 11, 6), date(2026, 11, 8))
        db.finish_run(self.conn, run_id, "success", {"sleep": {"fetched": 1}}, None)
        status = self.admin.execute("select status from garmin.sync_runs where id = %s", (run_id,)).fetchone()[0]
        self.assertEqual(status, "success")

    def test_garmin_sync_cannot_delete(self) -> None:
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            self.conn.execute("delete from garmin.raw_records")

    def test_anon_has_no_access(self) -> None:
        with self.assertRaises(psycopg.errors.InsufficientPrivilege):
            with self.admin.transaction():  # rolled back by the error
                self.admin.execute("set local role anon")
                self.admin.execute("select * from garmin.raw_records")

    def test_unknown_data_type_is_rejected(self) -> None:
        with self.assertRaises(psycopg.errors.CheckViolation):
            db.upsert_records(self.conn, "not_a_type", [("x", None, {})])


if __name__ == "__main__":
    unittest.main()
