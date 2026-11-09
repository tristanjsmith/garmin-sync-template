"""Minimal client for the Garmin Connect Personal API.

This module calls only the endpoints that the sync uses.
Authentication: the sync sends the Personal API key (env GARMIN_API_KEY) to
Garmin and gets a short-lived bearer token at the start of each run. If Garmin
rejects a request with HTTP 401, the client gets a new token one time.

Error messages from this module never contain response bodies, query values or
health data. They contain only the endpoint name, the HTTP status and a short
reason.
"""

from __future__ import annotations

import logging
import os
import time
from datetime import date, timedelta
from typing import Any

import requests

BASE_URL = "https://personal.connectapi.garmin.com"
TOKEN_PATH = "/personalapitoken-service/personal-api/personal-api-key/token"

REQUEST_TIMEOUT_SECONDS = 30
MIN_SECONDS_BETWEEN_REQUESTS = 1.0
MAX_RETRIES = 5  # waits 2, 4, 8, 16, 32 s unless the server sends Retry-After
MAX_RETRY_AFTER_SECONDS = 120

RANGE_CHUNK_DAYS = 31  # daily summaries, sleep (documented max) and HRV
ACTIVITY_PAGE_SIZE = 99  # documented default page size
MAX_ACTIVITY_PAGES = 200  # safety stop for pagination

log = logging.getLogger("garmin_client")


class GarminApiError(Exception):
    """An API call failed. The message never contains health data."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GarminClient:
    def __init__(self, api_key: str | None = None) -> None:
        key = (api_key if api_key is not None else os.environ.get("GARMIN_API_KEY", "")).strip()
        if not key:
            raise GarminApiError("GARMIN_API_KEY is not set")
        self._api_key = key
        self._session = requests.Session()
        self._token: str | None = None
        self._last_request_at = 0.0
        self.request_count = 0

    # ------------------------------------------------------------------ auth

    def authenticate(self) -> None:
        """Exchange the API key for a bearer token."""
        response = self._send(
            "POST",
            TOKEN_PATH,
            label="token",
            headers={"Accept": "*/*", "Authorization": f"ApiKey {self._api_key}"},
        )
        if response.status_code in (401, 403):
            raise GarminApiError(
                f"token: API key rejected (HTTP {response.status_code}); create a new key "
                "and update the GARMIN_API_KEY secret",
                response.status_code,
            )
        if not response.ok:
            raise GarminApiError(f"token: HTTP {response.status_code}", response.status_code)
        token = response.text.strip()
        if not token:
            raise GarminApiError("token: empty token response")
        self._token = token

    # ------------------------------------------------------------- transport

    def _throttle(self) -> None:
        wait = MIN_SECONDS_BETWEEN_REQUESTS - (time.monotonic() - self._last_request_at)
        if wait > 0:
            time.sleep(wait)

    def _send(
        self,
        method: str,
        path: str,
        *,
        label: str,
        headers: dict[str, str],
        params: dict[str, Any] | None = None,
    ) -> requests.Response:
        """Send one request with throttling and retries on 429, 5xx and network errors."""
        for attempt in range(MAX_RETRIES + 1):
            self._throttle()
            self._last_request_at = time.monotonic()
            self.request_count += 1
            try:
                response = self._session.request(
                    method,
                    BASE_URL + path,
                    headers=headers,
                    params=params,
                    timeout=REQUEST_TIMEOUT_SECONDS,
                )
            except (requests.ConnectionError, requests.Timeout) as exc:
                if attempt == MAX_RETRIES:
                    raise GarminApiError(f"{label}: network error ({type(exc).__name__})") from None
                delay = 2 ** (attempt + 1)
                log.warning("%s: network error, retry %d/%d in %ds", label, attempt + 1, MAX_RETRIES, delay)
                time.sleep(delay)
                continue

            retryable = response.status_code == 429 or response.status_code >= 500
            if not retryable or attempt == MAX_RETRIES:
                return response
            delay = _retry_after_seconds(response) or 2 ** (attempt + 1)
            log.warning(
                "%s: HTTP %d, retry %d/%d in %ds",
                label, response.status_code, attempt + 1, MAX_RETRIES, delay,
            )
            time.sleep(delay)
        raise AssertionError("unreachable")

    def _get(self, path: str, *, label: str, params: dict[str, Any] | None = None) -> Any:
        """Authenticated GET returning decoded JSON (None for an empty body)."""
        if self._token is None:
            self.authenticate()
        refreshed = False
        while True:
            response = self._send(
                "GET",
                path,
                label=label,
                params=params,
                headers={"Accept": "application/json", "Authorization": f"Bearer {self._token}"},
            )
            if response.status_code == 401 and not refreshed:
                log.info("%s: HTTP 401, refreshing token once", label)
                self.authenticate()
                refreshed = True
                continue
            break
        if not response.ok:
            raise GarminApiError(f"{label}: HTTP {response.status_code}", response.status_code)
        if not response.content:
            return None
        try:
            return response.json()
        except ValueError:
            raise GarminApiError(f"{label}: response was not valid JSON") from None

    # ------------------------------------------------------------- endpoints

    def daily_summaries(self, start: date, end: date) -> list[dict]:
        """GET /usersummary-service/v2/dailysummaries, 31-day chunks."""
        records: list[dict] = []
        for chunk_start, chunk_end in date_chunks(start, end, RANGE_CHUNK_DAYS):
            body = self._get(
                "/usersummary-service/v2/dailysummaries",
                label="daily_summary",
                params={"startDate": chunk_start.isoformat(), "endDate": chunk_end.isoformat()},
            )
            if body is None:
                continue
            if not isinstance(body, dict):
                raise GarminApiError("daily_summary: unexpected response shape")
            records.extend(_list_of_dicts(body.get("data"), "daily_summary"))
        return records

    def sleep_summaries(self, start: date, end: date) -> list[dict]:
        """GET /sleep-service/sleep/dailySleepSummariesByDate, 31-day chunks (documented max)."""
        records: list[dict] = []
        for chunk_start, chunk_end in date_chunks(start, end, RANGE_CHUNK_DAYS):
            body = self._get(
                "/sleep-service/sleep/dailySleepSummariesByDate",
                label="sleep",
                params={"startDate": chunk_start.isoformat(), "endDate": chunk_end.isoformat()},
            )
            records.extend(_list_of_dicts(body, "sleep"))
        return records

    def hrv_summaries(self, start: date, end: date) -> list[dict]:
        """GET /hrv-service/hrv/daily/{fromDate}/{toDate}, 31-day chunks."""
        records: list[dict] = []
        for chunk_start, chunk_end in date_chunks(start, end, RANGE_CHUNK_DAYS):
            body = self._get(
                f"/hrv-service/hrv/daily/{chunk_start.isoformat()}/{chunk_end.isoformat()}",
                label="hrv",
            )
            if body is None:
                continue
            if not isinstance(body, dict):
                raise GarminApiError("hrv: unexpected response shape")
            records.extend(_list_of_dicts(body.get("hrvSummaries"), "hrv"))
        return records

    def activities(self, start: date, end: date, activity_type: str) -> list[dict]:
        """GET /activitylist-service/activities/search/activities for one parent
        activity type (e.g. running, cycling), paginated 99 at a time."""
        records: list[dict] = []
        for page in range(MAX_ACTIVITY_PAGES):
            body = self._get(
                "/activitylist-service/activities/search/activities",
                label="activity",
                params={
                    "start": page * ACTIVITY_PAGE_SIZE,
                    "limit": ACTIVITY_PAGE_SIZE,
                    "startDate": start.isoformat(),
                    "endDate": end.isoformat(),
                    "activityType": activity_type,
                    "sortOrder": "asc",
                },
            )
            batch = _list_of_dicts(body, "activity")
            records.extend(batch)
            if len(batch) < ACTIVITY_PAGE_SIZE:
                return records
        raise GarminApiError("activity: too many pages, stopped for safety")

    def activity_detail(self, activity_id: int | str) -> dict | None:
        """GET /activity-service/activity/{activityId}. Returns None if the
        activity no longer exists (HTTP 404)."""
        try:
            body = self._get(f"/activity-service/activity/{int(activity_id)}", label="activity_detail")
        except GarminApiError as exc:
            if exc.status == 404:
                return None
            raise
        if not isinstance(body, dict):
            raise GarminApiError("activity_detail: unexpected response shape")
        return body

    def fitness_age(self, as_of: date) -> Any:
        """GET /fitnessage-service/fitnessage/v2/{calendarDate}: latest fitness
        age as of the given date."""
        return self._get(f"/fitnessage-service/fitnessage/v2/{as_of.isoformat()}", label="fitness_age")

    def heart_rate_zones(self) -> Any:
        """GET /biometric-service/heartRateZones/v2: current HR zone settings."""
        return self._get("/biometric-service/heartRateZones/v2", label="hr_zones")


# ---------------------------------------------------------------- helpers


def date_chunks(start: date, end: date, size_days: int) -> list[tuple[date, date]]:
    """Split an inclusive date range into inclusive chunks of at most size_days."""
    chunks = []
    cursor = start
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=size_days - 1), end)
        chunks.append((cursor, chunk_end))
        cursor = chunk_end + timedelta(days=1)
    return chunks


def _list_of_dicts(value: Any, label: str) -> list[dict]:
    if value is None:
        return []
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise GarminApiError(f"{label}: unexpected response shape")
    return value


def _retry_after_seconds(response: requests.Response) -> int | None:
    value = response.headers.get("Retry-After", "").strip()
    if value.isdigit():
        return max(1, min(int(value), MAX_RETRY_AFTER_SECONDS))
    return None
