"""Tests for the Garmin API client. They use the fake Garmin server."""

from __future__ import annotations

import unittest
from datetime import date

from helpers import (
    API_KEY, CYCLING_COUNT, MISSING_ACTIVITY_ID, RUNNING_COUNT, SENTINEL, FakeGarminTestCase,
)

import garmin_client
from garmin_client import GarminApiError, GarminClient, date_chunks

START, END = date(2026, 10, 1), date(2026, 11, 8)


class DateChunksTest(unittest.TestCase):
    def test_chunks_cover_the_range_without_gaps(self) -> None:
        chunks = date_chunks(START, END, 31)
        self.assertEqual(chunks[0][0], START)
        self.assertEqual(chunks[-1][1], END)
        for (_, first_end), (second_start, _) in zip(chunks, chunks[1:], strict=False):
            self.assertEqual((second_start - first_end).days, 1)
        for first, last in chunks:
            self.assertLessEqual((last - first).days + 1, 31)

    def test_one_day(self) -> None:
        self.assertEqual(date_chunks(END, END, 31), [(END, END)])


class ClientTest(FakeGarminTestCase):
    def test_daily_summaries_use_31_day_chunks(self) -> None:
        records = GarminClient().daily_summaries(START, END)
        self.assertEqual(len(records), (END - START).days + 1)
        self.assertEqual(self.fake.requests.count("/usersummary-service/v2/dailysummaries"), 2)

    def test_retry_after_429_and_500(self) -> None:
        self.fake.fail_first["/sleep-service"] = [429, 500]
        records = GarminClient().sleep_summaries(END, END)
        self.assertEqual(len(records), 1)

    def test_stop_after_max_retries(self) -> None:
        self.fake.fail_first["/hrv-service"] = [503] * (garmin_client.MAX_RETRIES + 1)
        with self.assertRaises(GarminApiError) as ctx:
            GarminClient().hrv_summaries(END, END)
        self.assertIn("HTTP 503", str(ctx.exception))
        self.assertNotIn(str(SENTINEL), str(ctx.exception))

    def test_new_token_after_401(self) -> None:
        self.fake.fail_first["/hrv-service"] = [401]
        GarminClient().hrv_summaries(END, END)
        self.assertEqual(self.fake.token_count, 2)

    def test_rejected_api_key(self) -> None:
        with self.assertRaises(GarminApiError) as ctx:
            GarminClient(api_key="wrong-key").authenticate()
        self.assertIn("API key rejected", str(ctx.exception))
        self.assertNotIn("wrong-key", str(ctx.exception))
        self.assertNotIn(API_KEY, str(ctx.exception))

    def test_activity_pages(self) -> None:
        client = GarminClient()
        self.assertEqual(len(client.activities(START, END, "running")), RUNNING_COUNT)
        self.assertEqual(len(client.activities(START, END, "cycling")), CYCLING_COUNT)

    def test_missing_activity_detail(self) -> None:
        self.assertIsNone(GarminClient().activity_detail(MISSING_ACTIVITY_ID))

    def test_unexpected_response_shape(self) -> None:
        def wrong_shape(handler) -> bool:
            handler.send(200, {"not": "a list", "value": SENTINEL})
            return True

        self.fake.overrides["/sleep-service"] = wrong_shape
        with self.assertRaises(GarminApiError) as ctx:
            GarminClient().sleep_summaries(END, END)
        self.assertIn("unexpected response shape", str(ctx.exception))
        self.assertNotIn(str(SENTINEL), str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
