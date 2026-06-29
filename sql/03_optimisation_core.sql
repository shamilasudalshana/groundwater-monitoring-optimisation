-- ============================================================================
--  03_optimisation_core.sql       Run as geodin2pg_etl_user.
--
--  The boss-aligned engine: config tables + the variable grid + the single
--  comprehensive recommendation view. v_optimisation_qgis is the ONE layer to
--  load in QGIS — it carries every per-filter fact, every quality metric, the
--  four sub-scores, the total, the class and the decision. No second table
--  needed in QGIS.
--
--  Order: run after 01_filter_bewertung.sql and 02_filter_quality.sql.
--  All CREATE ... IF NOT EXISTS / OR REPLACE -> safely re-runnable.
-- ============================================================================

-- CONFIG 1: projects in scope -------------------------------------------------
CREATE TABLE IF NOT EXISTS gw_analysis.cfg_projects (prj_id text PRIMARY KEY);
INSERT INTO gw_analysis.cfg_projects (prj_id) VALUES ('KDDLHC'), ('STBLHC')
ON CONFLICT DO NOTHING;

-- CONFIG 2: horizon bands + 4 weights + gap rule + mandatory toggle -----------
CREATE TABLE IF NOT EXISTS gw_analysis.cfg_horizon (
    horizon           text PRIMARY KEY,
    depth_min         numeric NOT NULL,
    depth_max         numeric NOT NULL,
    w_timeseries      numeric NOT NULL DEFAULT 0.40,
    w_parameter       numeric NOT NULL DEFAULT 0.30,
    w_quality         numeric NOT NULL DEFAULT 0.15,
    w_operation       numeric NOT NULL DEFAULT 0.15,
    gap_priority_max  int     NOT NULL DEFAULT 2,
    mandatory_enabled boolean NOT NULL DEFAULT true
);
INSERT INTO gw_analysis.cfg_horizon (horizon, depth_min, depth_max, mandatory_enabled) VALUES
    ('oberer', 0, 50, true), ('mittlerer', 50, 100, false), ('tieferer', 100, 100000, true)
ON CONFLICT (horizon) DO NOTHING;

-- CONFIG 3: score classes (score -> label/decision) ---------------------------
CREATE TABLE IF NOT EXISTS gw_analysis.cfg_score_class (
    min_score numeric PRIMARY KEY,
    label     text NOT NULL,
    decision  text
);
INSERT INTO gw_analysis.cfg_score_class (min_score, label, decision) VALUES
    (75, 'sehr gut',    'behalten_bevorzugt'),
    (55, 'gut',         'behalten'),
    (35, 'mittel',      'pruefen'),
    ( 1, 'gering',      'schwach'),
    ( 0, 'keine Daten', 'keine_daten')
ON CONFLICT (min_score) DO NOTHING;

-- CONFIG 4: variable grid (from QGIS step 04) ---------------------------------
CREATE TABLE IF NOT EXISTS gw_analysis.grid_cells (
    cell_id        bigserial PRIMARY KEY,
    horizon        text NOT NULL,
    drawdown_class int,
    priority       int,
    grid_m         numeric,
    geom           geometry(Polygon, 4647)
);
CREATE INDEX IF NOT EXISTS idx_grid_cells_geom ON gw_analysis.grid_cells USING gist (geom);
CREATE INDEX IF NOT EXISTS idx_grid_cells_hz   ON gw_analysis.grid_cells (horizon);

-- CONFIG 5: mandatory areas (pflichtbereiche), optional, per horizon ----------
CREATE TABLE IF NOT EXISTS gw_analysis.mandatory_areas (
    area_id bigserial PRIMARY KEY,
    horizon text NOT NULL,
    label   text,
    geom    geometry(Polygon, 4647)
);
CREATE INDEX IF NOT EXISTS idx_mandatory_geom ON gw_analysis.mandatory_areas USING gist (geom);

-- ============================================================================
--  Drop dependent views first (clean recreate; order matters).
-- ============================================================================
DROP VIEW IF EXISTS gw_analysis.v_optimisation_qgis;
DROP VIEW IF EXISTS gw_analysis.v_optimisation;
DROP VIEW IF EXISTS gw_analysis.v_gap_cells;

-- ============================================================================
--  MAIN VIEW  (single comprehensive recommendation layer)
-- ============================================================================
CREATE VIEW gw_analysis.v_optimisation AS
WITH scoped AS (
    SELECT f.*, c.horizon, c.w_timeseries, c.w_parameter, c.w_operation, c.w_quality,
           c.mandatory_enabled
    FROM gw_analysis.v_filter_quality_enriched f
    JOIN gw_analysis.cfg_projects p ON p.prj_id = f.prj_id
    JOIN gw_analysis.cfg_horizon  c
      ON f.filter_mid_depth_m >= c.depth_min AND f.filter_mid_depth_m < c.depth_max
),
celled AS (
    SELECT s.*, gc.cell_id, gc.drawdown_class, gc.priority, gc.grid_m
    FROM scoped s
    LEFT JOIN gw_analysis.grid_cells gc
      ON gc.horizon = s.horizon AND ST_Within(s.geom, gc.geom)
),
flagged AS (
    SELECT c.*,
        (c.mandatory_enabled AND EXISTS (
            SELECT 1 FROM gw_analysis.mandatory_areas m
            WHERE m.horizon = c.horizon AND ST_Within(c.geom, m.geom)
        )) AS is_mandatory
    FROM celled c
),
scored AS (
    SELECT f.*,
        -- 1) time series: record length + continuity
        CASE WHEN NOT f.has_gw_levels THEN 0 ELSE
            0.6 * (CASE WHEN f.gw_record_length_years >= 10 THEN 100
                        WHEN f.gw_record_length_years >= 5  THEN 80
                        WHEN f.gw_record_length_years >= 2  THEN 50
                        WHEN f.gw_record_length_years >  0  THEN 20 ELSE 0 END)
          + 0.4 * (CASE f.gw_continuity_status
                        WHEN 'continuous_or_no_major_gap' THEN 100
                        WHEN 'minor_gaps'    THEN 70
                        WHEN 'major_gaps'    THEN 40
                        WHEN 'discontinuous' THEN 20 ELSE 30 END)
        END AS sc_ts,
        -- 2) parameters: what it measures
        CASE WHEN f.has_gw_levels AND f.has_water_quality THEN 100
             WHEN f.has_gw_levels        THEN 70
             WHEN f.has_water_quality    THEN 50
             ELSE 0 END AS sc_param,
        -- 3) operation: usable / accessible
        CASE f.operational_status
             WHEN 'aktiv'       THEN 100
             WHEN 'unbekannt'   THEN 60
             WHEN 'stillgelegt' THEN 25
             WHEN 'rueckgebaut' THEN 0
             ELSE 60 END AS sc_ops,
        -- 4) quality & density: frequency minus a capped jump penalty.
        --    (Homogeneity is INFORMATIONAL only — it flags artificial steps for
        --     review but is NOT penalised, because a real trend is not a defect.)
        CASE WHEN NOT f.has_gw_levels THEN 0 ELSE GREATEST(0,
            (CASE WHEN f.n_per_year >= 12 THEN 100
                  WHEN f.n_per_year >= 4  THEN 75
                  WHEN f.n_per_year >= 1  THEN 45
                  WHEN f.n_per_year >  0  THEN 20 ELSE 0 END)
            - LEAST(30, COALESCE(f.jump_rate, 0) * 100)
        ) END AS sc_quality
    FROM flagged f
),
total AS (
    SELECT s.*,
        ROUND( ( (s.w_timeseries*s.sc_ts + s.w_parameter*s.sc_param
                  + s.w_operation*s.sc_ops + s.w_quality*s.sc_quality)
                 / NULLIF(s.w_timeseries + s.w_parameter + s.w_operation + s.w_quality, 0)
               )::numeric, 1) AS score_total
    FROM scored s
),
ranked AS (
    SELECT t.*,
        bool_or(t.is_mandatory) OVER (PARTITION BY t.cell_id) AS mand_in_cell,
        ROW_NUMBER() OVER (
            PARTITION BY t.cell_id
            ORDER BY t.is_mandatory DESC, t.score_total DESC,
                     t.gw_record_length_years DESC NULLS LAST,
                     t.n_gw_levels DESC, t.n_water_quality DESC, t.filter_id
        ) AS rank_in_cell
    FROM total t
)
SELECT
    -- identity --------------------------------------------------------------
    ranked.horizon, ranked.prj_id, ranked.locid, ranked.station_id,
    ranked.filter_id, ranked.filter_invid,
    ranked.short_name, ranked.long_name, ranked.filter_name, ranked.invkenn,
    ranked.monitoring_type, ranked.n_filters_at_station,
    ranked.is_top_filter, ranked.company_meas_filter,
    -- depth / horizon -------------------------------------------------------
    ranked.filter_top_m, ranked.filter_bottom_m, ranked.filter_mid_depth_m, ranked.depth_flag,
    -- grid ------------------------------------------------------------------
    ranked.cell_id, ranked.drawdown_class, ranked.priority, ranked.grid_m,
    -- groundwater-level time series -----------------------------------------
    ranked.n_gw_levels, ranked.gw_record_length_years, ranked.first_gw_year, ranked.last_gw_year,
    ranked.max_gap_days, ranked.n_gaps_over_2_years, ranked.gw_continuity_status, ranked.has_gw_levels,
    -- water quality ---------------------------------------------------------
    ranked.n_water_quality, ranked.n_wq_parameters, ranked.last_wq_year, ranked.has_water_quality,
    -- operational status (curated) ------------------------------------------
    ranked.operational_status, ranked.dismantled, ranked.decommission_date,
    ranked.accessible, ranked.operator_owner, ranked.monitoring_network,
    -- quality metrics (n_per_year + jump SCORED; rest INFORMATIONAL) --------
    ranked.n_per_year, ranked.jump_rate, ranked.homogeneity_flag,
    ranked.outlier_rate, ranked.drilling_year,
    -- sub-scores + total ----------------------------------------------------
    ROUND(ranked.sc_ts, 1)      AS score_timeseries,
    ROUND(ranked.sc_param, 1)   AS score_parameter,
    ROUND(ranked.sc_quality, 1) AS score_quality,
    ROUND(ranked.sc_ops, 1)     AS score_operation,
    ranked.score_total,
    scls.label    AS score_klasse,
    scls.decision AS score_decision,
    -- decision --------------------------------------------------------------
    ranked.is_mandatory, ranked.rank_in_cell,
    CASE
        WHEN ranked.cell_id IS NULL  THEN 'ausserhalb_absenkungszone'
        WHEN ranked.is_mandatory     THEN 'pflicht_behalten'
        WHEN ranked.mand_in_cell     THEN 'redundant_pruefen'        -- cell already covered by a mandatory well
        WHEN ranked.rank_in_cell = 1 THEN 'behalten_beste_im_raster' -- 1st choice (kept)
        WHEN ranked.rank_in_cell = 2 THEN 'alternative_2'            -- 2nd choice
        WHEN ranked.rank_in_cell = 3 THEN 'alternative_3'            -- 3rd choice
        ELSE 'redundant_pruefen'
    END AS entscheid,
    -- human-readable one-liner ----------------------------------------------
    format('GW: %s Werte (%s-%s), ~%s/Jahr; WQ: %s; Tiefe %s m; Status: %s',
           ranked.n_gw_levels, COALESCE(ranked.first_gw_year::text,'?'),
           COALESCE(ranked.last_gw_year::text,'?'),
           COALESCE(ROUND(ranked.n_per_year,1)::text,'?'),
           ranked.n_water_quality, ranked.filter_mid_depth_m, ranked.operational_status) AS info,
    ranked.geom
FROM ranked
LEFT JOIN LATERAL (
    SELECT label, decision FROM gw_analysis.cfg_score_class c
    WHERE ranked.score_total >= c.min_score
    ORDER BY c.min_score DESC LIMIT 1
) scls ON true;

-- ============================================================================
--  GAP VIEW
-- ============================================================================
CREATE OR REPLACE VIEW gw_analysis.v_gap_cells AS
SELECT gc.cell_id, gc.horizon, gc.drawdown_class, gc.priority, gc.grid_m, gc.geom
FROM gw_analysis.grid_cells gc
JOIN gw_analysis.cfg_horizon c ON c.horizon = gc.horizon
WHERE gc.priority <= c.gap_priority_max
  AND NOT EXISTS (
      SELECT 1 FROM gw_analysis.v_filter_bewertung f
      JOIN gw_analysis.cfg_projects p ON p.prj_id = f.prj_id
      WHERE f.filter_mid_depth_m >= c.depth_min AND f.filter_mid_depth_m < c.depth_max
        AND ST_Within(f.geom, gc.geom)
  );

-- ============================================================================
--  QGIS LAYER: the single layer to load. Unique gid so the view loads cleanly;
--  pick 'gid' as the feature id in QGIS.
-- ============================================================================
CREATE OR REPLACE VIEW gw_analysis.v_optimisation_qgis AS
SELECT row_number() OVER (ORDER BY horizon, cell_id, filter_id) AS gid, *
FROM gw_analysis.v_optimisation;
