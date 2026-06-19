-- ============================================================================
--  ONE-TIME SETUP  —  run this whole file ONCE, connected as `postgres`
--  (or whoever owns the hydro_db database).
--
--  It creates two schemas and the manual curation table, then hands ownership
--  to geodin2pg_etl_user so that ALL further work (views, queries, editing the
--  curation table) is done as your normal least-privilege user — never as
--  postgres again.
--
--  Why CREATE SCHEMA failed for geodin2pg_etl_user:
--  creating a schema needs the CREATE privilege ON THE DATABASE. You granted
--  CONNECT on the database and CREATE only inside the geodin_raw / hydro
--  schemas, so the user could not create a new schema. This file fixes that
--  once, from a privileged role.
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 1. Schemas, owned by your normal user
--    gw_analysis  = DERIVED / computed objects (the evaluation views)
--    hydro_manual = HUMAN-curated source facts the ETL must never overwrite
-- ----------------------------------------------------------------------------
CREATE SCHEMA IF NOT EXISTS gw_analysis  AUTHORIZATION geodin2pg_etl_user;
CREATE SCHEMA IF NOT EXISTS hydro_manual AUTHORIZATION geodin2pg_etl_user;

-- ----------------------------------------------------------------------------
-- 2. Manual operational-status table
--    Keyed on filter_invid (stable GeoDIN key) — NOT on the serial filter_id,
--    which can change if hydro.filter is ever rebuilt by the ETL.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hydro_manual.filter_status (
    filter_invid        text PRIMARY KEY,        -- = hydro.filter.invid
    operational_status  text,                    -- 'aktiv' | 'stillgelegt' | 'rueckgebaut' | 'unbekannt'
    dismantled          boolean,                 -- convenience flag (true = physically removed)
    decommission_date   date,
    accessible          boolean,                 -- can it still be measured?
    operator_owner      text,                    -- who operates / owns it
    monitoring_network  text,                    -- which network it belongs to (if any)
    note                text,
    info_source         text,                    -- where this came from (Wasserfassung, site visit, ...)
    updated_by          text,
    updated_at          timestamptz NOT NULL DEFAULT now()
);

COMMENT ON TABLE hydro_manual.filter_status IS
    'Human-curated operational status per filter. NOT produced by the ETL; '
    'survives ETL re-runs. Joined into gw_analysis.v_filter_bewertung by filter_invid.';

-- Postgres created these objects, so transfer ownership to the working user
-- so it can SELECT/INSERT/UPDATE/DELETE freely without further grants.
ALTER TABLE hydro_manual.filter_status OWNER TO geodin2pg_etl_user;

-- ----------------------------------------------------------------------------
-- After running this file as postgres, reconnect as geodin2pg_etl_user
-- and run gw_analysis_v_filter_bewertung.sql. You will not need postgres again
-- for this pipeline.
-- ----------------------------------------------------------------------------
