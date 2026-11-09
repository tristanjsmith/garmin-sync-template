"""Tests for complete dry runs. They use the fake Garmin server and no database."""

from __future__ import annotations

import logging
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import CYCLING_COUNT, RUNNING_COUNT, SENTINEL, FakeGarminTestCase

import settings
import sync


class DryRunTest(FakeGarminTestCase):
    def run_sync(self, *args: str, settings_text: str | None = None) -> tuple[int, str]:
        if settings_text is not None:
            handle = tempfile.NamedTemporaryFile("w", suffix=".toml", delete=False)
            handle.write(settings_text)
            handle.close()
            patcher = mock.patch.object(settings, "SETTINGS_FILE", Path(handle.name))
            patcher.start()
            self.addCleanup(patcher.stop)
        with self.assertLogs(level=logging.INFO) as logs:
            code = sync.main(["--mode", "dry_run", *args])
        output = "\n".join(logs.output)
        self.assertNotIn(str(SENTINEL), output, "a health value is in the logs")
        self.assertNotIn("987654", output, "a health value is in the logs")
        return code, output

    def test_success(self) -> None:
        code, output = self.run_sync("--days", "3")
        self.assertEqual(code, 0)
        self.assertIn("finished: status=success", output)
        self.assertIn(f"activity: fetched={RUNNING_COUNT + CYCLING_COUNT} ", output)
        self.assertIn(f"activity_detail: fetched={RUNNING_COUNT - 1} ", output)  # one activity sends HTTP 404
        self.assertIn("fields=calendarDate, heartRate, uuid", output)

    def test_detail_only_for_selected_types(self) -> None:
        code, output = self.run_sync(
            "--days", "1",
            settings_text='activity_types = ["running", "cycling"]\ndetail_activity_types = []\n',
        )
        self.assertEqual(code, 0)
        self.assertIn("activity_detail: fetched=0 ", output)
        self.assertFalse(any(p.startswith("/activity-service/") for p in self.fake.requests))

    def test_incorrect_settings_stop_the_run(self) -> None:
        code, output = self.run_sync(settings_text="activity_types = [running\n")
        self.assertEqual(code, 1)
        self.assertIn("settings.toml", output)
        self.assertEqual(self.fake.requests, [])

    def test_records_without_a_date_are_skipped(self) -> None:
        def one_without_date(handler) -> bool:
            handler.send(200, [
                {"calendarDate": "2026-11-07", "deepSleepSeconds": SENTINEL},
                {"calendarDate": None, "deepSleepSeconds": SENTINEL},
            ])
            return True

        self.fake.overrides["/sleep-service"] = one_without_date
        code, output = self.run_sync("--days", "1")
        self.assertEqual(code, 0)
        self.assertIn("sleep: skipped 1 of 2 records without a valid calendarDate (NoneType=1)", output)

    def test_one_failed_type_gives_partial(self) -> None:
        def wrong_shape(handler) -> bool:
            handler.send(200, {"not": "a list"})
            return True

        self.fake.overrides["/sleep-service"] = wrong_shape
        code, output = self.run_sync("--days", "1")
        self.assertEqual(code, 1)
        self.assertIn("finished: status=partial", output)
        self.assertIn("hrv: fetched=1 ", output)

    def test_rejected_api_key_gives_failed(self) -> None:
        with mock.patch.dict("os.environ", {"GARMIN_API_KEY": "wrong-key"}):
            code, output = self.run_sync("--days", "1")
        self.assertEqual(code, 1)
        self.assertIn("finished: status=failed", output)
        self.assertNotIn("wrong-key", output)


if __name__ == "__main__":
    unittest.main()
