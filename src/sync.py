"""garmin-sync entry point.

Usage:  python src/sync.py [--mode MODE] [--days N]
Env:    MODE (scheduled | manual | backfill | dry_run, default manual)
        DAYS (default 3; backfill always uses 365)
        GARMIN_API_KEY, DATABASE_URL (DATABASE_URL not needed for dry_run)
File:   settings.toml (activity types to sync)

Logs contain only data types, date ranges, counts, sizes, field names,
durations, status and sanitised error messages: never health values.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any
from collections.abc import Callable

import settings as settings_module
from garmin_client import GarminApiError, GarminClient

MODES = ("scheduled", "manual", "backfill", "dry_run")
BACKFILL_DAYS = 365
MAX_DAYS = 400

DATA_TYPES = ("daily_summary", "sleep", "hrv", "activity", "activity_detail", "user_metrics")
FITNESS_AGE_STEP_DAYS = 7  # fitness age sampled weekly back from date_to

log = logging.getLogger("sync")

Record = tuple[str, date | None, Any]  # (source_id, calendar_date, payload)


class RecordError(Exception):
    """A record could not be mapped. The message never contains values."""


# ------------------------------------------------------------------ mapping


def _parse_date(value: Any, what: str) -> date:
    if not isinstance(value, str) or len(value) < 10:
        raise RecordError(f"{what} is missing or not a date")
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        raise RecordError(f"{what} is not a date") from None


def _by_calendar_date(items: list[dict], data_type: str) -> list[Record]:
    """source_id = calendar_date = the record's calendarDate (one record per day).

    Records without a valid calendarDate can't be keyed, so they are skipped and
    counted. Only the *kind* of value found is logged (e.g. NoneType, str(len=0)),
    never the value. If every record lacks a valid date, the type fails, because
    that means the response format differs from the docs."""
    records = []
    skipped: dict[str, int] = {}
    for item in items:
        value = item.get("calendarDate")
        try:
            day = _parse_date(value, f"{data_type} calendarDate")
        except RecordError:
            kind = f"str(len={len(value)})" if isinstance(value, str) else type(value).__name__
            if "calendarDate" not in item:
                kind = "absent"
            skipped[kind] = skipped.get(kind, 0) + 1
            continue
        records.append((day.isoformat(), day, item))
    if skipped:
        summary = ", ".join(f"{kind}={n}" for kind, n in sorted(skipped.items()))
        log.warning(
            "%s: skipped %d of %d records without a valid calendarDate (%s)",
            data_type, sum(skipped.values()), len(items), summary,
        )
        if not records:
            raise RecordError(f"{data_type}: no record has a valid calendarDate")
    return records


def _activity_record(item: dict) -> Record:
    activity_id = item.get("activityId")
    if not isinstance(activity_id, int):
        raise RecordError("activity activityId is missing")
    day = _parse_date(item.get("startTimeLocal"), "activity startTimeLocal")
    return (str(activity_id), day, item)


def _dedupe(records: list[Record]) -> list[Record]:
    """Keep the last record per source_id (an upsert can't touch a row twice)."""
    return list({r[0]: r for r in records}.values())


# --------------------------------------------------------------- fetchers


def fetch_daily_summary(client: GarminClient, start: date, end: date) -> list[Record]:
    return _dedupe(_by_calendar_date(client.daily_summaries(start, end), "daily_summary"))


def fetch_sleep(client: GarminClient, start: date, end: date) -> list[Record]:
    return _dedupe(_by_calendar_date(client.sleep_summaries(start, end), "sleep"))


def fetch_hrv(client: GarminClient, start: date, end: date) -> list[Record]:
    return _dedupe(_by_calendar_date(client.hrv_summaries(start, end), "hrv"))


def fetch_activities(
    client: GarminClient, start: date, end: date, cfg: settings_module.Settings
) -> tuple[list[Record], list[Record]]:
    """Returns (all activities of the configured types, the ones that need detail)."""
    all_records: list[Record] = []
    for_detail: list[Record] = []
    for activity_type in cfg.activity_types:
        records = [_activity_record(item) for item in client.activities(start, end, activity_type)]
        log.info("activity: type=%s fetched=%d", activity_type, len(records))
        all_records.extend(records)
        if activity_type in cfg.detail_activity_types:
            for_detail.extend(records)
    return _dedupe(all_records), _dedupe(for_detail)


def fetch_activity_details(client: GarminClient, activities: list[Record]) -> list[Record]:
    records = []
    missing = 0
    for source_id, list_date, _ in activities:
        detail = client.activity_detail(source_id)
        if detail is None:
            missing += 1
            continue
        summary = detail.get("summaryDTO") if isinstance(detail.get("summaryDTO"), dict) else {}
        start_local = summary.get("startTimeLocal")
        day = _parse_date(start_local, "activity_detail startTimeLocal") if start_local else list_date
        records.append((source_id, day, detail))
    if missing:
        log.warning("activity_detail: %d activities no longer exist (HTTP 404), skipped", missing)
    return records


def fetch_user_metrics(client: GarminClient, start: date, end: date) -> list[Record]:
    """Fitness age (weekly back from `end`) and today's HR zone settings."""
    records: list[Record] = []
    day = end
    while day >= start:
        body = client.fitness_age(day)
        if body:  # skip empty responses
            records.append((f"fitness_age:{day.isoformat()}", day, body))
        day -= timedelta(days=FITNESS_AGE_STEP_DAYS)
    zones = client.heart_rate_zones()
    if zones:
        today = datetime.now(timezone.utc).date()
        records.append((f"hr_zones:{today.isoformat()}", today, zones))
    return records


# ------------------------------------------------------------------ logging


def _payload_stats(records: list[Record]) -> tuple[float, list[str]]:
    """Average payload size in KB and sorted top-level field names (names only)."""
    if not records:
        return 0.0, []
    total_bytes = 0
    names: set[str] = set()
    for _, _, payload in records:
        total_bytes += len(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
        if isinstance(payload, dict):
            names.update(payload.keys())
        elif isinstance(payload, list):
            names.add("[list]")
            for item in payload:
                if isinstance(item, dict):
                    names.update(f"[].{key}" for key in item.keys())
    return total_bytes / len(records) / 1024, sorted(names)


def _safe_error(exc: BaseException) -> str:
    """Describe an exception without any values that could be health data."""
    if isinstance(exc, (GarminApiError, RecordError)):
        return str(exc)
    sqlstate = getattr(exc, "sqlstate", None)
    if sqlstate:
        return f"{type(exc).__name__} (SQLSTATE {sqlstate})"
    return type(exc).__name__


# --------------------------------------------------------------------- main


def _parse_args(argv: list[str]) -> tuple[str, int]:
    parser = argparse.ArgumentParser(description="Sync Garmin data into Supabase.")
    parser.add_argument("--mode", default=os.environ.get("MODE") or "manual", choices=MODES)
    parser.add_argument("--days", type=int, default=int(os.environ.get("DAYS") or 3))
    args = parser.parse_args(argv)
    days = BACKFILL_DAYS if args.mode == "backfill" else args.days
    if not 1 <= days <= MAX_DAYS:
        parser.error(f"--days must be between 1 and {MAX_DAYS}")
    return args.mode, days


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s", stream=sys.stdout
    )
    mode, days = _parse_args(sys.argv[1:] if argv is None else argv)
    try:
        cfg = settings_module.load()
    except settings_module.SettingsError as exc:
        log.error("%s", exc)
        return 1
    dry_run = mode == "dry_run"
    date_to = datetime.now(timezone.utc).date()
    date_from = date_to - timedelta(days=days - 1)
    log.info("start: mode=%s date_from=%s date_to=%s days=%d", mode, date_from, date_to, days)
    log.info(
        "settings: activity_types=%s detail_activity_types=%s",
        ",".join(cfg.activity_types) or "(none)", ",".join(cfg.detail_activity_types) or "(none)",
    )
    started = time.monotonic()

    conn = None
    run_id = None
    if not dry_run:
        import db  # psycopg is only needed when writing

        if not os.environ.get("DATABASE_URL", "").strip():
            log.error("database: DATABASE_URL secret is not set")
            return 1
        try:
            conn = db.connect()
            run_id = db.start_run(conn, mode, date_from, date_to)
        except Exception as exc:  # noqa: BLE001
            log.error("database: could not start run: %s", _safe_error(exc))
            return 1
        log.info("sync_runs id=%d", run_id)

    counts: dict[str, dict[str, int]] = {}
    errors: dict[str, str] = {}
    auth_error: str | None = None

    try:
        client = GarminClient()
        client.authenticate()
    except Exception as exc:  # noqa: BLE001
        client = None
        auth_error = _safe_error(exc)
        log.error("auth: %s", auth_error)

    def process(data_type: str, fetch: Callable[[], list[Record]]) -> None:
        t0 = time.monotonic()
        try:
            records = fetch()
            if dry_run:
                avg_kb, fields = _payload_stats(records)
                counts[data_type] = {"fetched": len(records)}
                log.info(
                    "%s: fetched=%d avg_kb=%.1f duration_s=%.1f fields=%s",
                    data_type, len(records), avg_kb, time.monotonic() - t0, ", ".join(fields),
                )
            else:
                counts[data_type] = db.upsert_records(conn, data_type, records)
                c = counts[data_type]
                log.info(
                    "%s: fetched=%d inserted=%d updated=%d unchanged=%d duration_s=%.1f",
                    data_type, c["fetched"], c["inserted"], c["updated"], c["unchanged"],
                    time.monotonic() - t0,
                )
        except Exception as exc:  # noqa: BLE001
            errors[data_type] = _safe_error(exc)
            log.error("%s: failed: %s", data_type, errors[data_type])

    if client is not None:
        process("daily_summary", lambda: fetch_daily_summary(client, date_from, date_to))
        process("sleep", lambda: fetch_sleep(client, date_from, date_to))
        process("hrv", lambda: fetch_hrv(client, date_from, date_to))

        for_detail: list[Record] | None = None

        def activity_fetch() -> list[Record]:
            nonlocal for_detail
            all_records, for_detail = fetch_activities(client, date_from, date_to, cfg)
            return all_records

        process("activity", activity_fetch)
        if for_detail is None:
            errors["activity_detail"] = "skipped because activity failed"
            log.error("activity_detail: skipped because activity failed")
        else:
            process("activity_detail", lambda: fetch_activity_details(client, for_detail))
        process("user_metrics", lambda: fetch_user_metrics(client, date_from, date_to))
        log.info("api requests made: %d", client.request_count)

    if auth_error is not None or len(errors) == len(DATA_TYPES):
        status = "failed"
    elif errors:
        status = "partial"
    else:
        status = "success"
    if auth_error is not None:
        error_text = f"auth: {auth_error}"
    else:
        # Error messages already start with the data type name.
        error_text = "; ".join(v if v.startswith(f"{k}:") else f"{k}: {v}" for k, v in errors.items()) or None

    if conn is not None and run_id is not None:
        try:
            db.finish_run(conn, run_id, status, counts, error_text)
        except Exception as exc:  # noqa: BLE001
            log.error("database: could not finish run: %s", _safe_error(exc))
            status = "failed"
        finally:
            conn.close()

    log.info("finished: status=%s duration_s=%.1f", status, time.monotonic() - started)
    return 0 if status == "success" else 1


if __name__ == "__main__":
    sys.exit(main())
