# Operations

## Run modes

To start a run:

1. In your repository, select **Actions**.
2. Select **garmin-sync**.
3. Select **Run workflow**.
4. Set **Run mode** and **Days to fetch**.
5. Select **Run workflow**.

| Run mode | Days to fetch | Function |
|---|---|---|
| `dry_run` | 1 to 400 | Gets data. Does not write to the database. Logs the counts, the average size and the field names. Does not use `DATABASE_URL`. |
| `manual` | 1 to 400 | Gets and writes data for the number of days, up to today |
| `backfill` | Ignored | Gets and writes data for the last 365 days |
| `scheduled` | Ignored | The daily automatic run uses this mode. Do not select it. |

You can run a mode again. The sync does not write duplicate rows.
The sync updates a row only when the data from Garmin changes.

---

## Read the result of a run

1. Select the run.
2. Select **sync**.
3. Open **Run sync**.

Each data type has one line. Examples:

| Line | Meaning |
|---|---|
| `daily_summary: fetched=3 inserted=1 updated=0 unchanged=2` | Correct |
| `sleep: skipped 1 of 3 records without a valid calendarDate (NoneType=1)` | Garmin sent a record without a date. The sync did not write it. This is usually an empty record. |
| `sleep: failed: <reason>` | This data type failed. The sync continued with the other data types. |
| `finished: status=success` | All data types are correct |
| `finished: status=partial` | One or more data types failed |
| `finished: status=failed` | All data types failed |

If the status is not `success`, the run has a red mark. GitHub can send you an email.

The table `garmin.sync_runs` also keeps the status and the errors of each run.

---

## Errors

| Message | Cause | Action |
|---|---|---|
| `auth: token: API key rejected` | The Garmin key is not correct, or it expired | Make a new key. Update the `GARMIN_API_KEY` secret. |
| `HTTP 429, retry …` | Garmin asks the sync to send fewer requests | No action. The sync tries again automatically, up to 5 times. |
| `HTTP 5xx, retry …` | Garmin has a temporary server problem | No action. The sync tries again automatically, up to 5 times. |
| `unexpected response shape` | Garmin changed the API | Compare the response with the Garmin API documentation. Change the code. |
| `database: DATABASE_URL secret is not set` | The secret is missing | Add the secret. Make sure that the name is `DATABASE_URL`. |
| `database: could not start run` | The `DATABASE_URL` is not correct, or the Supabase project is paused | Do step 6 of SETUP.md again. Make sure that the project is active. |
| `settings.toml: …` | `settings.toml` is not correct | Read the message. Correct the file. |
| `activity_detail: skipped because activity failed` | The `activity` data type failed | Correct the `activity` error first |

The logs do not contain health values. You can share the log lines to get help.

---

## Change the Garmin key

1. Sign in to Garmin Connect.
2. Go to **Settings** > **Personal API Token**.
3. Make a new key.
4. Delete the old key.
5. In your repository, select **Settings** > **Secrets and variables** > **Actions**.
6. Select `GARMIN_API_KEY`.
7. Select **Update**.
8. Paste the new key.
9. Select **Update secret**.
10. Do a `dry_run` with 1 day to make sure that the key is correct.

---

## Change the database password

1. In the Supabase **SQL Editor**, run this command. Replace `NEW_PASSWORD` with a new password:

   ```sql
   alter role garmin_sync with password 'NEW_PASSWORD';
   ```

2. Use only letters and digits in the password.
3. Change the password in your `DATABASE_URL`.
4. In your repository, update the `DATABASE_URL` secret.
5. Do a `manual` run with 1 day to make sure that the password is correct.

---

## Change the time of the daily run

1. Open `.github/workflows/sync.yml`.
2. Find this line:

   ```yaml
   - cron: "30 9 * * *" # 09:30 UTC daily, after the watch syncs
   ```

3. Change the time. The format is `minute hour * * *`. The time is UTC.
4. Commit the change.

---

## Free plan limits

| Service | Limit | Use by this tool |
|---|---|---|
| Supabase Free database | 500 MB | Approximately 2 to 10 MB each year |
| Supabase Free project pause | Supabase can pause a project after approximately 1 week with no activity | The daily run usually prevents this. If Supabase pauses the project, restore it in the Supabase dashboard. |
| GitHub Actions, private repository, Free plan | 2,000 minutes each month | Approximately 1 minute each day |
| Garmin Personal API | Garmin does not publish limits | The sync waits 1 second between requests. A daily run sends approximately 10 requests. A backfill sends approximately 200 requests. |

---

## Updates

Dependabot opens a pull request each month when there is a new version of a dependency.
Dependabot proposes only versions that are 14 days old or more.

1. Read the pull request.
2. Merge the pull request.
3. Do a `dry_run` with 1 day to make sure that the sync is correct.
