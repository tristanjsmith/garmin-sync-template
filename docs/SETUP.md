# Setup procedure

Do the steps in sequence.
You can do all the steps in a web browser.

## Before you start

You must have these accounts:

| Account | Plan | Use |
|---|---|---|
| GitHub | Free | Keeps the code and runs the sync each day |
| Supabase | Free | Keeps your data in a Postgres database |
| Garmin Connect | Any | Supplies your data |

> **CAUTION:** Garmin controls access to the Garmin Connect Personal API.
> Make sure that your Garmin Connect account can make a Personal API key before you start (step 7).

---

## Step 1: Make your repository

1. On the template repository page, select **Use this template**.
2. Select **Create a new repository**.
3. Type a name. Example: `garmin-sync`.
4. Set the visibility to **Private**.

> **WARNING:** Do not use a public repository.
> In a public repository, all persons can read the run logs.

5. Select **Create repository**.

---

## Step 2: Make your Supabase project

1. Go to supabase.com. Sign in.
2. Select **New project**.
3. Type a project name.
4. Type a database password. Keep this password in a password manager.
5. Select the region that is nearest to you.
6. Select **Create new project**.
7. Wait until the project is ready.

> **NOTE:** The sync does not use the Supabase Data API.
> If the Data API is on, do not add the `garmin` schema to **Exposed schemas**.

---

## Step 3: Make the database tables

1. Open the file `supabase/migrations/001_init.sql` in your repository.
2. Select **Raw**.
3. Copy all of the text.
4. In Supabase, open **SQL Editor**.
5. Select **New query**.
6. Paste the text.
7. Select **Run**.
8. Make sure that the result shows **Success**.

This SQL makes these items:

- The schema `garmin`.
- The table `garmin.raw_records`. It keeps your Garmin data.
- The table `garmin.sync_runs`. It keeps a record of each run.
- The database user `garmin_sync`. This user can only read, add and update rows in the two tables. This user cannot delete data.

---

## Step 4: Set the password of the `garmin_sync` user

1. Make a new password. Use 24 to 32 characters.

> **CAUTION:** Use only letters (A–Z, a–z) and digits (0–9).
> Other characters (for example `@ : / ? # %`) cause errors in the database URL.

2. In the Supabase **SQL Editor**, select **New query**.
3. Type this command. Replace `NEW_PASSWORD` with your password:

   ```sql
   alter role garmin_sync with password 'NEW_PASSWORD';
   ```

4. Select **Run**.
5. Keep the password in a password manager.

> **WARNING:** Do not type this password in a chat, an issue or a file in the repository.

---

## Step 5: Make sure that the database setup is correct

1. In the Supabase **SQL Editor**, select **New query**.
2. Paste these commands:

   ```sql
   select relname, relrowsecurity from pg_class
   where relnamespace = 'garmin'::regnamespace and relkind = 'r';

   select table_name, privilege_type from information_schema.role_table_grants
   where grantee = 'garmin_sync' order by 1, 2;

   select rolname, rolcanlogin, rolsuper, rolbypassrls from pg_roles
   where rolname = 'garmin_sync';
   ```

3. Select **Run**.
4. Make sure that the results agree with this table:

| Command | Correct result |
|---|---|
| First | 2 rows: `raw_records` and `sync_runs`. `relrowsecurity` is `true` for both. |
| Second | 6 rows: `INSERT`, `SELECT` and `UPDATE` for each table. No `DELETE`. |
| Third | 1 row: `rolcanlogin` is `true`. `rolsuper` is `false`. `rolbypassrls` is `false`. |

---

## Step 6: Make the database URL

1. In Supabase, select **Connect** (top of the project page).
2. Select **Direct**.
3. Select **Session pooler**.

> **NOTE:** Use the Session pooler. GitHub Actions uses IPv4.
> The direct connection uses IPv6 only on the Free plan.

4. Find the URI. It has this format:

   ```
   postgresql://postgres.PROJECT_REF:[YOUR-PASSWORD]@HOST:5432/postgres
   ```

5. Write a new URI in a password manager. Use this format:

   ```
   postgresql://garmin_sync.PROJECT_REF:PASSWORD@HOST:5432/postgres?sslmode=require
   ```

6. Make these changes to the URI from Supabase:

| Part | Change |
|---|---|
| `postgres.` before `PROJECT_REF` | Replace with `garmin_sync.` |
| `[YOUR-PASSWORD]` | Replace with the password from step 4. Do not keep the brackets. |
| End of the URI | Add `?sslmode=require` |
| `HOST`, `:5432` and `/postgres` | Do not change |

> **CAUTION:** Do not change the `/postgres` at the end of the URI. It is the database name.
> Change only the user name at the start.

This URI is your `DATABASE_URL`.

---

## Step 7: Make a Garmin Personal API key

1. Sign in to Garmin Connect in a web browser.
2. Go to **Settings** > **Personal API Token**.
3. Make a new key.
4. Copy the key.
5. Keep the key in a password manager.
6. If the page shows an expiry date, write down the date.

> **WARNING:** Do not type the key in a chat, an issue or a file in the repository.

---

## Step 8: Add the secrets to your repository

1. In your repository on GitHub, select **Settings**.
2. Select **Secrets and variables** > **Actions**.
3. Select **New repository secret**.
4. Add the two secrets in this table. Type each name exactly as shown.

| Name | Value |
|---|---|
| `GARMIN_API_KEY` | The key from step 7 |
| `DATABASE_URL` | The URI from step 6 |

After you save a secret, GitHub does not show it again. This is correct.

---

## Step 9: Select the activity types

1. In your repository, open the file `settings.toml`.
2. Read the comments in the file.
3. If necessary, select the pencil icon and change the lists.
4. Select **Commit changes**.

The default setting gets running and cycling activities.
It gets the full detail for running activities only.

---

## Step 10: Do the first runs

Do the three runs in sequence.
For each run, do these steps:

1. In your repository, select **Actions**.
2. Select **garmin-sync**.
3. Select **Run workflow**.
4. Set **Run mode** and **Days to fetch** as shown in the table.
5. Select **Run workflow**.
6. Wait until the run is complete.
7. Make sure that the run has a green check mark.

| Run | Run mode | Days to fetch | Result |
|---|---|---|---|
| 1 | `dry_run` | `3` | The sync gets data. It does not write to the database. |
| 2 | `manual` | `3` | The sync writes 3 days of data. |
| 3 | `backfill` | (ignored) | The sync writes 365 days of data. This takes 5 to 10 minutes. |

To read the result of a run:

1. Select the run.
2. Select **sync**.
3. Open **Run sync**.
4. Make sure that the last line is `finished: status=success`.

If a run fails, read [OPERATIONS.md](OPERATIONS.md).

After run 3, the sync runs automatically each day at 09:30 UTC.

---

## Step 11 (optional): Recommended GitHub settings

1. Get emails when a run fails:
   1. On GitHub, open your profile **Settings**.
   2. Select **Notifications**.
   3. Under **Actions**, select **Only notify for failed workflows**.
2. Make sure that all actions use a full commit SHA:
   1. In your repository, select **Settings** > **Actions** > **General**.
   2. Select **Require actions to be pinned to a full-length commit SHA**.
   3. Select **Save**.
