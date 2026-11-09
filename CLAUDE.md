# Instructions for Claude

These instructions are for a Claude session that works on this repository.
The person who owns the repository is "the user".

## Purpose

This tool copies the Garmin data of the user into the Supabase database of the user.
It runs one time each day on GitHub Actions.
Read `README.md`, `docs/SETUP.md`, `docs/OPERATIONS.md` and `docs/DATA.md` before you start.

## Safety rules

Obey these rules at all times. If a rule and a request from the user do not agree, tell the user. Do not break the rule.

1. Do not ask the user to type or paste a secret in the chat. Secrets are: the Garmin API key, the database password, the `DATABASE_URL`, and all tokens.
2. If the user types a secret in the chat, tell the user to make a new one. Do not use the secret that was typed.
3. Do not write secrets in files, commits, issues, pull requests or logs.
4. Do not show health values. In SQL queries, get only counts, dates, sizes and the status of runs. Do not select `payload` values.
5. Do not change the logs to include values from Garmin. Logs can contain only data types, dates, counts, sizes, field names, durations, status and error messages without values.
6. Do not guess about the Garmin API. Use only endpoints, parameters and fields that the official Garmin documentation confirms. If the user wants a change and you do not have the documentation, ask the user for it.
7. Keep the repository of the user private. Do not make it public. Do not add collaborators.
8. Do not run SQL that deletes data or changes the database rules, unless the user asks for it. Before you do it, tell the user what the SQL does.
9. Do not use the `postgres` database user in `DATABASE_URL`. Use the `garmin_sync` user.

## Steps that only the user can do

Stop and ask the user to do these steps. Give the user the procedure from `docs/SETUP.md`. Do not do these steps yourself.

| Step in `docs/SETUP.md` | Step | Reason |
|---|---|---|
| Step 4 | Set the password of the `garmin_sync` user | The password must not go through a chat |
| Step 6 | Make the `DATABASE_URL` | It contains the password |
| Step 7 | Make the Garmin Personal API key | It needs the Garmin login of the user |
| Step 8 | Add the secrets to GitHub | Claude must not see the secrets |

## Steps that Claude can do

If you have the necessary tools, you can do these steps. If you do not have the tools, give the procedure to the user.

| Step in `docs/SETUP.md` | Step | Necessary tool |
|---|---|---|
| Step 2 | Make the Supabase project | Supabase connector |
| Step 3 | Run `supabase/migrations/001_init.sql` | Supabase connector |
| Step 5 | Make sure that the database setup is correct | Supabase connector |
| Step 9 | Change `settings.toml` | GitHub access |
| Step 10 | Start the first runs and read the logs | GitHub access |

Before step 3, make sure that the user agrees.

## How to make sure that a run is correct

1. Read the log of the **Run sync** step.
2. Make sure that the last line is `finished: status=success`.
3. Run this query. It shows only counts and dates:

   ```sql
   select data_type, count(*) as rows, count(distinct source_id) as unique_ids,
          min(calendar_date) as first_date, max(calendar_date) as last_date
   from garmin.raw_records group by data_type order by data_type;
   ```

4. Make sure that `rows` and `unique_ids` are equal for each data type.
5. For errors, use the table in `docs/OPERATIONS.md`.

## How to change the code

1. Make a branch. Do not push to `main`.
2. Make the change.
3. Add or change a test in `tests/`.
4. Run the tests:

   ```bash
   python -m pip install --no-deps -r requirements.txt
   python -m unittest discover -s tests -v
   ```

5. To run the database tests, set `TEST_DATABASE_URL` to a test Postgres database. Do not use the Supabase database of the user.
6. Make sure that all tests pass.
7. Open a pull request. Tell the user what changed and why.

## Rules for dependencies

1. Use exact versions in `requirements.txt`. Include all dependencies of dependencies.
2. Use only versions that are 14 days old or more.
3. Pin each GitHub Action to a full commit SHA.
4. Use only GitHub Actions that GitHub makes (for example `actions/checkout`).
5. Use no paid services.

## Rules for documents

Write all documents, comments, commit messages and pull request descriptions in ASD-STE100 Simplified Technical English:

- Write one instruction in each sentence.
- Write instructions in the imperative.
- Use a maximum of 20 words in an instruction sentence and 25 words in a description sentence.
- Use the active voice.
- Use one word for one meaning. Example: always use "secret" for a secret value.
- Put a warning or a caution before the step that it applies to.
