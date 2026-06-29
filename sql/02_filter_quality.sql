-- ============================================================================
--  02_filter_quality.sql        Run as geodin2pg_etl_user.
--
--  Per-filter time-series QUALITY metrics, computed by
--  scripts/compute_filter_quality.py into gw_analysis.filter_quality, plus the
--  enriched view that adds them to the base facts.
--
--  Order: run after 01_filter_bewertung.sql, before 03_optimisation_core.sql.
-- ============================================================================

-- table populated by compute_filter_quality.py
CREATE TABLE IF NOT EXISTS gw_analysis.filter_quality (
    filter_invid     text PRIMARY KEY,        -- = hydro.filter.invid
    n_per_year       numeric,                 -- measurement frequency  (SCORED)
    jump_rate        numeric,                 -- 0..1 implausible-jump fraction (SCORED, penalty)
    outlier_rate     numeric,                 -- 0..1 robust IQR outlier fraction (INFO only)
    homogeneity_flag text,                    -- detrended break flag  (INFO only)
                                              --   'ok' | 'break_pruefen' | 'insufficient'
    drilling_year    int,                     -- INFO only
    n_used           int,                     -- points the stats are based on
    computed_at      timestamptz NOT NULL DEFAULT now()
);

-- base facts + quality metrics, one row per filter (all projects)
CREATE OR REPLACE VIEW gw_analysis.v_filter_quality_enriched AS
SELECT b.*,
       q.n_per_year,
       q.jump_rate,
       q.outlier_rate,
       q.homogeneity_flag,
       q.drilling_year
FROM gw_analysis.v_filter_bewertung b
LEFT JOIN gw_analysis.filter_quality q ON q.filter_invid = b.filter_invid;
