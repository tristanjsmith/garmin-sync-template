-- garmin-sync: initial schema, role and access rules.
--
-- Run this file one time in the Supabase SQL Editor (see docs/SETUP.md).
-- You can run it again without problems. Each statement is idempotent.
--
-- Do not expose the `garmin` schema through the Data API.
-- If the Data API is on, "Exposed schemas" must NOT include `garmin`.
-- The revoke statements below are a second protection.

begin;

-- ---------------------------------------------------------------------------
-- Schema
-- ---------------------------------------------------------------------------
create schema if not exists garmin;

-- ---------------------------------------------------------------------------
-- Tables
-- ---------------------------------------------------------------------------
create table if not exists garmin.raw_records (
    data_type     text        not null,
    source_id     text        not null,
    calendar_date date,
    payload       jsonb       not null,
    fetched_at    timestamptz not null default now(),
    constraint raw_records_pkey primary key (data_type, source_id),
    constraint raw_records_data_type_check check (
        data_type in (
            'daily_summary', 'sleep', 'hrv',
            'activity', 'activity_detail', 'user_metrics'
        )
    )
);

create index if not exists raw_records_data_type_calendar_date_idx
    on garmin.raw_records (data_type, calendar_date);

create table if not exists garmin.sync_runs (
    id          bigserial   primary key,
    started_at  timestamptz not null default now(),
    finished_at timestamptz,
    status      text,
    mode        text,
    date_from   date,
    date_to     date,
    counts      jsonb,
    error       text,
    constraint sync_runs_status_check check (
        status in ('running', 'success', 'partial', 'failed')
    ),
    constraint sync_runs_mode_check check (
        mode in ('scheduled', 'manual', 'backfill', 'dry_run')
    )
);

-- ---------------------------------------------------------------------------
-- Lock down: nothing for public / anon / authenticated
-- ---------------------------------------------------------------------------
revoke all on schema garmin from public, anon, authenticated;
revoke all on all tables    in schema garmin from public, anon, authenticated;
revoke all on all sequences in schema garmin from public, anon, authenticated;
revoke all on all functions in schema garmin from public, anon, authenticated;

-- Make sure anything created later in this schema is not auto-granted either.
alter default privileges in schema garmin
    revoke all on tables    from public, anon, authenticated;
alter default privileges in schema garmin
    revoke all on sequences from public, anon, authenticated;
alter default privileges in schema garmin
    revoke all on functions from public, anon, authenticated;

-- ---------------------------------------------------------------------------
-- Role garmin_sync (LOGIN, password set separately, never in SQL)
-- ---------------------------------------------------------------------------
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'garmin_sync') then
        create role garmin_sync
            login
            nosuperuser nocreatedb nocreaterole noreplication nobypassrls
            noinherit;
    else
        alter role garmin_sync
            login
            nosuperuser nocreatedb nocreaterole noreplication nobypassrls
            noinherit;
    end if;
end
$$;

-- Grant only what the sync needs.
grant usage on schema garmin to garmin_sync;
grant select, insert, update on garmin.raw_records to garmin_sync;
grant select, insert, update on garmin.sync_runs   to garmin_sync;
grant usage on sequence garmin.sync_runs_id_seq    to garmin_sync;

-- ---------------------------------------------------------------------------
-- Row Level Security: only garmin_sync may read/write rows
-- ---------------------------------------------------------------------------
alter table garmin.raw_records enable row level security;
alter table garmin.sync_runs   enable row level security;

drop policy if exists raw_records_garmin_sync_select on garmin.raw_records;
drop policy if exists raw_records_garmin_sync_insert on garmin.raw_records;
drop policy if exists raw_records_garmin_sync_update on garmin.raw_records;

create policy raw_records_garmin_sync_select on garmin.raw_records
    for select to garmin_sync using (true);
create policy raw_records_garmin_sync_insert on garmin.raw_records
    for insert to garmin_sync with check (true);
create policy raw_records_garmin_sync_update on garmin.raw_records
    for update to garmin_sync using (true) with check (true);

drop policy if exists sync_runs_garmin_sync_select on garmin.sync_runs;
drop policy if exists sync_runs_garmin_sync_insert on garmin.sync_runs;
drop policy if exists sync_runs_garmin_sync_update on garmin.sync_runs;

create policy sync_runs_garmin_sync_select on garmin.sync_runs
    for select to garmin_sync using (true);
create policy sync_runs_garmin_sync_insert on garmin.sync_runs
    for insert to garmin_sync with check (true);
create policy sync_runs_garmin_sync_update on garmin.sync_runs
    for update to garmin_sync using (true) with check (true);

commit;

-- After applying, set the password separately (not in this file), e.g. in the
-- Supabase SQL editor:  alter role garmin_sync with password '<new password>';
