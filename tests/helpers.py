"""Test helpers: a fake Garmin server.

The fake server sends test data only. It does not contain real health data.
Each numeric test value is SENTINEL. The tests make sure that SENTINEL is
never in the logs.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import unittest
from collections.abc import Callable
from datetime import date, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

import garmin_client  # noqa: E402

SENTINEL = 987654.321
API_KEY = "test-api-key"
RUNNING_COUNT = 150  # more than one page of 99
CYCLING_COUNT = 2
MISSING_ACTIVITY_ID = 1003  # the fake server sends HTTP 404 for this activity

Override = Callable[["Handler"], bool]


def _dates(start: str, end: str) -> list[date]:
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


class Handler(BaseHTTPRequestHandler):
    server: FakeGarminServer

    def log_message(self, *args) -> None:  # silence the HTTP server
        pass

    def send(self, status: int, body=None, headers: dict | None = None, raw: bytes | None = None) -> None:
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else b"")
        self.send_response(status)
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self) -> None:
        fake = self.server.fake
        if urlparse(self.path).path != garmin_client.TOKEN_PATH:
            return self.send(404)
        if self.headers.get("Authorization") != f"ApiKey {API_KEY}":
            return self.send(401)
        fake.token_count += 1
        self.send(200, raw=f"token-{fake.token_count}".encode())

    def do_GET(self) -> None:
        fake = self.server.fake
        url = urlparse(self.path)
        path, query = url.path, parse_qs(url.query)
        fake.requests.append(path)

        if not self.headers.get("Authorization", "").startswith("Bearer token-"):
            return self.send(401)
        for prefix, statuses in fake.fail_first.items():
            if path.startswith(prefix) and statuses:
                status = statuses.pop(0)
                return self.send(status, {"error": SENTINEL}, {"Retry-After": "1"} if status == 429 else None)
        for prefix, override in fake.overrides.items():
            if path.startswith(prefix) and override(self):
                return

        if path == "/usersummary-service/v2/dailysummaries":
            days = _dates(query["startDate"][0], query["endDate"][0])
            return self.send(200, {"data": [
                {"calendarDate": d.isoformat(), "uuid": "u", "heartRate": {"restingValue": SENTINEL}} for d in days
            ]})
        if path == "/sleep-service/sleep/dailySleepSummariesByDate":
            days = _dates(query["startDate"][0], query["endDate"][0])
            return self.send(200, [
                {"id": i, "calendarDate": d.isoformat(), "deepSleepSeconds": SENTINEL} for i, d in enumerate(days)
            ])
        if path.startswith("/hrv-service/hrv/daily/"):
            start, end = path.split("/")[-2:]
            return self.send(200, {"hrvSummaries": [
                {"calendarDate": d.isoformat(), "lastNightAvg": SENTINEL} for d in _dates(start, end)
            ]})
        if path == "/activitylist-service/activities/search/activities":
            activity_type = query["activityType"][0]
            count, base = (RUNNING_COUNT, 1000) if activity_type == "running" else (CYCLING_COUNT, 5000)
            items = [{
                "activityId": base + i,
                "startTimeLocal": f"2026-11-0{1 + i % 7} 07:00:00",
                "activityType": {"typeKey": activity_type},
                "averageHR": SENTINEL,
            } for i in range(count)]
            start, limit = int(query["start"][0]), int(query["limit"][0])
            return self.send(200, items[start:start + limit])
        if path.startswith("/activity-service/activity/"):
            activity_id = int(path.rsplit("/", 1)[1])
            if activity_id == MISSING_ACTIVITY_ID:
                return self.send(404)
            return self.send(200, {
                "activityId": activity_id,
                "summaryDTO": {"startTimeLocal": "2026-11-02T07:00:00.0", "averageHR": SENTINEL},
            })
        if path.startswith("/fitnessage-service/fitnessage/v2/"):
            return self.send(200, {"fitnessAge": SENTINEL, "chronologicalAge": 30})
        if path == "/biometric-service/heartRateZones/v2":
            return self.send(200, [{"sport": "RUNNING", "zone1Floor": SENTINEL}])
        self.send(404)


class FakeGarminServer(ThreadingHTTPServer):
    fake: FakeGarmin


class FakeGarmin:
    """A fake Garmin API on a local port."""

    def __init__(self) -> None:
        self.requests: list[str] = []
        self.token_count = 0
        self.fail_first: dict[str, list[int]] = {}
        self.overrides: dict[str, Override] = {}
        self._server = FakeGarminServer(("127.0.0.1", 0), Handler)
        self._server.fake = self
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self._server.server_port}"

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._server.shutdown()
        self._server.server_close()


class FakeGarminTestCase(unittest.TestCase):
    """Starts a fake Garmin server for each test. Removes all waits."""

    def setUp(self) -> None:
        self.fake = FakeGarmin()
        self.fake.start()
        self.addCleanup(self.fake.stop)
        for patcher in (
            mock.patch.object(garmin_client, "BASE_URL", self.fake.url),
            mock.patch.object(garmin_client, "MIN_SECONDS_BETWEEN_REQUESTS", 0),
            mock.patch.object(garmin_client.time, "sleep", lambda seconds: None),
            mock.patch.dict(os.environ, {"GARMIN_API_KEY": API_KEY}),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)
