# Data

## Tables

The tool writes to two tables in the schema `garmin`.

### `garmin.raw_records`

Each row is one record from Garmin.

| Column | Contents |
|---|---|
| `data_type` | One of: `daily_summary`, `sleep`, `hrv`, `activity`, `activity_detail`, `user_metrics` |
| `source_id` | The key of the record. See the next table. |
| `calendar_date` | The local date of the record |
| `payload` | The record from Garmin, without changes (JSON) |
| `fetched_at` | The time of the last change to the row |

The primary key is (`data_type`, `source_id`). Thus, the table cannot have duplicate records.

### `garmin.sync_runs`

Each row is one run of the tool.

| Column | Contents |
|---|---|
| `id` | Run number |
| `started_at`, `finished_at` | Start time and end time |
| `status` | `running`, `success`, `partial` or `failed` |
| `mode` | `scheduled`, `manual`, `backfill` or `dry_run` |
| `date_from`, `date_to` | The dates of the data |
| `counts` | For each data type: `fetched`, `inserted`, `updated`, `unchanged` |
| `error` | The errors. The errors contain no health values. |

---

## Data types

| Data type | Garmin endpoint | `source_id` | `calendar_date` |
|---|---|---|---|
| `daily_summary` | `/usersummary-service/v2/dailysummaries` | The date | `calendarDate` |
| `sleep` | `/sleep-service/sleep/dailySleepSummariesByDate` | The date | `calendarDate` |
| `hrv` | `/hrv-service/hrv/daily/{fromDate}/{toDate}` | The date | `calendarDate` |
| `activity` | `/activitylist-service/activities/search/activities` | `activityId` | The date of `startTimeLocal` |
| `activity_detail` | `/activity-service/activity/{activityId}` | `activityId` | The date of `summaryDTO.startTimeLocal` |
| `user_metrics` | `/fitnessage-service/fitnessage/v2/{date}` | `fitness_age:<date>` | The requested date |
| `user_metrics` | `/biometric-service/heartRateZones/v2` | `hr_zones:<date>` | The date of the run (UTC) |

The tool uses the date as the key for `daily_summary`, `sleep` and `hrv`.
The Garmin documentation does not say that the Garmin IDs of these records are stable.
The date is stable. Each day has one record.

---

## Notes about the data

- In `daily_summary`, the field `movement` (steps, floors) is a JSON text value, not a JSON object.
- In `activity`, each record contains `hrTimeInZone_1` to `hrTimeInZone_5` (seconds in each heart rate zone).
- In `activity`, each record can contain `vO2MaxValue`, `lactateThresholdBpm`, `activityTrainingLoad` and `fastestSplit_*` values.
- `splitSummaries` contains one summary for each split type. It does not contain each lap.
- The heart rate zone settings show only the current settings. Garmin does not supply a history. The tool keeps one record each day, so the history starts on the first run.
- The fitness age endpoint gives the latest value on a date. The backfill gets one value each week.
- Activity records can contain the names of other persons (comments, likes). The tool keeps the records without changes.

---

## Data that Garmin does not supply

The Garmin Connect Personal API does not supply these items:

- Each lap or each kilometre split of an activity. Only the activity file (`.FIT`) contains laps. This tool does not get activity files.
- Race predictions.
- Training status, and acute or chronic training load.
- A separate history of VO2 max and lactate threshold. The tool gets these values from each activity.
- Published rate limits, and the expiry of a Personal API key.
