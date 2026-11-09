# garmin-sync

This tool copies your Garmin data into your own Supabase Postgres database.
It runs one time each day on GitHub Actions.
It uses only free plans: GitHub Free and Supabase Free.

You can then use the data in your database for analysis and dashboards.
For example, you can connect Claude to the database with the Supabase connector.

> **WARNING:** This tool copies your health data into a database that you control.
> You are responsible for the security of your GitHub account, your Supabase project and your secrets.
> Do not make your copy of this repository public. Public repositories show the run logs to all persons.

## How to start

1. Select **Use this template** (top of this page).
2. Select **Create a new repository**.
3. Set the visibility to **Private**.
4. Do the procedure in [docs/SETUP.md](docs/SETUP.md).

The setup takes approximately 30 minutes.
You can do all the steps in a web browser.

## What the tool does

Each day at 09:30 UTC, the tool gets the data for the last 3 days.
It gets 3 days because a watch can sync late.
It writes the data to the table `garmin.raw_records`.
It writes a record of each run to the table `garmin.sync_runs`.

| Data type | Contents |
|---|---|
| `daily_summary` | Steps, resting heart rate, stress, Body Battery, calories, respiration |
| `sleep` | Sleep stages, sleep scores, sleep need, naps |
| `hrv` | Overnight HRV, weekly average, baseline, status |
| `activity` | A summary of each activity of the types in `settings.toml` |
| `activity_detail` | The full detail of each activity of the types in `detail_activity_types` |
| `user_metrics` | Fitness age (one value each week) and heart rate zone settings |

For more information about the data, read [docs/DATA.md](docs/DATA.md).

## How to select activity types

Edit the file [`settings.toml`](settings.toml). You can edit it on GitHub.

```toml
activity_types = ["running", "cycling"]
detail_activity_types = ["running"]
```

- `activity_types`: the sync gets the activities of these types.
- `detail_activity_types`: the sync gets the full detail for these types only.

The comments in `settings.toml` give the rules.

## Safety

- The tool keeps no secrets in the repository. You keep the secrets in GitHub Secrets.
- The logs contain no health values. They contain only data types, dates, counts, sizes, field names, durations and status.
- The tool connects to the database with a limited user (`garmin_sync`). This user cannot delete data.
- The tool uses an encrypted connection to the database.

## Documents

| Document | Contents |
|---|---|
| [docs/SETUP.md](docs/SETUP.md) | Procedure to set up the tool with your accounts |
| [docs/OPERATIONS.md](docs/OPERATIONS.md) | Procedures to run the tool, read failures and change secrets |
| [docs/DATA.md](docs/DATA.md) | Data that the tool stores, and data that Garmin does not supply |

## Licence

MIT. Read the [LICENSE](LICENSE) file.

This project is not related to Garmin Ltd. or Supabase Inc.
