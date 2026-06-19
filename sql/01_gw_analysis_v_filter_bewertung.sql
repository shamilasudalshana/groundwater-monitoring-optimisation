-- ============================================================================
--  gw_analysis.v_filter_bewertung
--  Filter-level evaluation view for the Wasserfassung monitoring-network
--  optimisation (boss-aligned "rank the existing filters first" approach).
--
--  ONE ROW PER FILTER (well screen) — not per station — because a single
--  station can carry several filters in different hydrogeological horizons.
--
--  Targets the NEW `hydro` schema (post-ETL). Horizont-agnostic: it exposes
--  filter_mid_depth_m and the data metrics; the horizon banding
--  (oberer 0-50 / mittlerer 50-100 / tieferer >100) is applied downstream
--  from config.py so the thresholds live in exactly one user-editable place.
--
--  PREREQUISITE: run 01_setup_as_postgres.sql once (creates the gw_analysis
--  and hydro_manual schemas + the manual status table). Then run THIS file
--  as geodin2pg_etl_user. It is freely re-runnable (CREATE OR REPLACE).
-- ============================================================================

CREATE OR REPLACE VIEW gw_analysis.v_filter_bewertung AS

-- ---------------------------------------------------------------------------
-- 1. Per-filter groundwater-level time-series facts (gaps, length, recency)
-- ---------------------------------------------------------------------------
WITH gw_gaps AS (
    SELECT
        filter_id,
        measured_at,
        measured_at - LAG(measured_at)
            OVER (PARTITION BY filter_id ORDER BY measured_at) AS gap_interval
    FROM hydro.gw_level
    WHERE measured_at IS NOT NULL
),
gw_stats AS (
    SELECT
        g.filter_id,
        COUNT(*)                                   AS n_gw_levels,
        EXTRACT(YEAR FROM MIN(g.measured_at))::int AS first_gw_year,
        EXTRACT(YEAR FROM MAX(g.measured_at))::int AS last_gw_year,
        ROUND( ( (MAX(g.measured_at)::date - MIN(g.measured_at)::date)
                 / 365.25 )::numeric , 1)          AS gw_record_length_years,
        ROUND( MAX(EXTRACT(EPOCH FROM g.gap_interval) / 86400.0)::numeric, 0)
                                                   AS max_gap_days,
        COUNT(*) FILTER (WHERE g.gap_interval > INTERVAL '730 days')
                                                   AS n_gaps_over_2_years
    FROM gw_gaps g
    GROUP BY g.filter_id
),

-- ---------------------------------------------------------------------------
-- 2. Per-filter water-quality facts (presence, count, breadth, recency)
-- ---------------------------------------------------------------------------
wq_stats AS (
    SELECT
        wq.filter_id,
        COUNT(*)                                   AS n_water_quality,
        COUNT(DISTINCT wq.parameter_code)          AS n_wq_parameters,
        EXTRACT(YEAR FROM MAX(wq.sampled_at))::int AS last_wq_year
    FROM hydro.water_quality wq
    WHERE wq.filter_id IS NOT NULL
    GROUP BY wq.filter_id
),

-- ---------------------------------------------------------------------------
-- 3. Filter + station base: geometry, names, and depth-sign handling
-- ---------------------------------------------------------------------------
filter_base AS (
    SELECT
        f.filter_id,
        f.invid                       AS filter_invid,
        f.station_id,
        f.prj_id,
        f.locid,
        st.short_name,
        st.long_name,
        f.filter_name,
        f.is_top_filter,
        f.company_meas_filter,
        f.invkenn,                                   -- GeoDIN INVKENN (code / Lfd.Nr.)
        f.monitoring_type,

        COUNT(*) OVER (PARTITION BY f.station_id)     AS n_filters_at_station,

        f.filter_top_m,
        f.filter_bottom_m,

        -- --- DEPTH-SIGN-SAFE MID DEPTH -------------------------------------
        -- Computed as recorded; suspicious records are flagged (depth_flag)
        -- rather than silently abs()'d, so a wrong sign surfaces for review.
        -- If your data's convention is fully consistent, switch to ABS() here.
        CASE
            WHEN f.filter_top_m IS NULL AND f.filter_bottom_m IS NULL THEN NULL
            ELSE ROUND( ( (COALESCE(f.filter_top_m, f.filter_bottom_m)
                         + COALESCE(f.filter_bottom_m, f.filter_top_m)) / 2.0 )::numeric, 2)
        END AS filter_mid_depth_m,

        CASE
            WHEN f.filter_top_m IS NULL AND f.filter_bottom_m IS NULL
                 THEN 'no_depth'
            WHEN COALESCE(f.filter_top_m, 0) < 0 OR COALESCE(f.filter_bottom_m, 0) < 0
                 THEN 'check_sign'
            WHEN f.filter_top_m IS NOT NULL AND f.filter_bottom_m IS NOT NULL
                 AND f.filter_top_m > f.filter_bottom_m
                 THEN 'check_order'
            WHEN GREATEST(COALESCE(f.filter_top_m, 0), COALESCE(f.filter_bottom_m, 0)) > 1000
                 THEN 'check_range'
            ELSE 'ok'
        END AS depth_flag,

        -- Geometry in EPSG:4647 (metric) for all grid / distance work.
        CASE
            WHEN st.epsg = 4647 THEN st.geom_native
            ELSE ST_Transform(st.geom, 4647)
        END AS geom
    FROM hydro.filter f
    JOIN hydro.station st
        ON st.station_id = f.station_id
)

-- ---------------------------------------------------------------------------
-- 4. Final assembly  (operational status now comes from hydro_manual)
-- ---------------------------------------------------------------------------
SELECT
    fb.filter_id,
    fb.filter_invid,
    fb.station_id,
    fb.prj_id,
    fb.locid,
    fb.short_name,
    fb.long_name,
    fb.filter_name,
    fb.invkenn,
    fb.monitoring_type,
    fb.n_filters_at_station,
    fb.is_top_filter,
    fb.company_meas_filter,

    -- depth / horizon basis
    fb.filter_top_m,
    fb.filter_bottom_m,
    fb.filter_mid_depth_m,
    fb.depth_flag,

    -- groundwater-level time series
    COALESCE(gs.n_gw_levels, 0)                 AS n_gw_levels,
    gs.first_gw_year,
    gs.last_gw_year,
    gs.gw_record_length_years,
    gs.max_gap_days,
    COALESCE(gs.n_gaps_over_2_years, 0)         AS n_gaps_over_2_years,
    (COALESCE(gs.n_gw_levels, 0) > 0)           AS has_gw_levels,

    CASE
        WHEN COALESCE(gs.n_gw_levels, 0) < 2          THEN 'insufficient'
        WHEN gs.max_gap_days <= 365                    THEN 'continuous_or_no_major_gap'
        WHEN gs.max_gap_days <= 730                    THEN 'minor_gaps'
        WHEN COALESCE(gs.n_gaps_over_2_years, 0) <= 1  THEN 'major_gaps'
        ELSE 'discontinuous'
    END AS gw_continuity_status,

    -- water quality
    COALESCE(wq.n_water_quality, 0)             AS n_water_quality,
    COALESCE(wq.n_wq_parameters, 0)            AS n_wq_parameters,
    wq.last_wq_year,
    (COALESCE(wq.n_water_quality, 0) > 0)      AS has_water_quality,

    -- operational status (human-curated; ETL never overwrites this)
    COALESCE(ms.operational_status, 'unbekannt') AS operational_status,
    ms.dismantled,
    ms.decommission_date,
    ms.accessible,
    ms.operator_owner,
    ms.monitoring_network,

    fb.geom
FROM filter_base fb
LEFT JOIN gw_stats gs              ON gs.filter_id    = fb.filter_id
LEFT JOIN wq_stats wq              ON wq.filter_id    = fb.filter_id
LEFT JOIN hydro_manual.filter_status ms ON ms.filter_invid = fb.filter_invid;

-- ============================================================================
-- USAGE
--   -- All filters for the joint KDDLHC + STBLHC run:
--   SELECT * FROM gw_analysis.v_filter_bewertung
--   WHERE prj_id IN ('KDDLHC', 'STBLHC');
--
--   -- Data-health check BEFORE trusting any horizon assignment:
--   SELECT depth_flag, COUNT(*) FROM gw_analysis.v_filter_bewertung
--   WHERE prj_id IN ('KDDLHC','STBLHC') GROUP BY depth_flag ORDER BY 2 DESC;
--
--   -- Seed the manual status table with these projects' filters (then edit):
--   INSERT INTO hydro_manual.filter_status (filter_invid, operational_status)
--   SELECT filter_invid, 'unbekannt'
--   FROM gw_analysis.v_filter_bewertung
--   WHERE prj_id IN ('KDDLHC','STBLHC')
--   ON CONFLICT (filter_invid) DO NOTHING;
-- ============================================================================
