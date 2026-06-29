# Groundwater Monitoring Network Optimisation

Configurable PostGIS/QGIS workflow to optimise groundwater monitoring networks
(Wasserfassung Messnetze) from GeoDIN data and drawdown models. It ranks the
**existing** monitoring filters by data value, thins redundancy within a
drawdown-scaled grid, and separately flags coverage gaps — producing one
reviewable recommendation layer for a senior hydrogeologist to sign off.

> Designed for explainability: every keep/redundant decision traces to a real
> filter and a readable reason, suitable for the Wasserfassung and the authorities.

---

## Method

Take all existing filters → score each on data value (time series, parameters,
**data quality & density**, operation) → drop them into a variable grid whose
cell size comes from the drawdown zone → within each cell keep the best (or the
mandatory) filter, flag the rest as redundant → separately flag high-priority
cells that contain no filter as coverage gaps. Everything runs per horizon
(oberer / mittlerer / tieferer) by configuration alone.

See `docs/bewertungslogik_scoring.md` for the full scoring logic.

---

## Architecture

```
GeoDIN (Access, master)
      │  ETL  (separate repo: geodin2pg_etl — read-only copy)
      ▼
PostgreSQL/PostGIS  hydro schema
      │
      ├── gw_analysis.v_filter_bewertung         per-filter facts (depth, time series, WQ, status)
      ├── gw_analysis.filter_quality             per-filter quality metrics (Python-computed)
      ├── gw_analysis.v_filter_quality_enriched  facts + quality  (internal building block)
      ├── gw_analysis.cfg_*                       config tables (projects, horizons, scores)
      ├── gw_analysis.grid_cells                  variable grid from QGIS steps 00–04
      ├── gw_analysis.v_optimisation             scored + decided recommendation  ← engine
      ├── gw_analysis.v_optimisation_qgis        THE single QGIS layer (everything + gid)
      └── gw_analysis.v_gap_cells                coverage gaps
      ▼
QGIS  (front-end: styles v_optimisation_qgis + v_gap_cells, prints the map)
```

In QGIS you load **one** layer — `v_optimisation_qgis` — and it carries every
fact, every quality metric, all four sub-scores, the total, the class and the
decision. `v_filter_quality_enriched` is an internal building block, not a
second layer to load.

---

## Repository layout

```
.
├── .env.example          copy to .env (gitignored) and fill in
├── .gitignore
├── README.md
├── docs/
│   └── bewertungslogik_scoring.md   scoring reference (read this to change scores)
├── sql/
│   ├── 00_setup_as_postgres.sql     schemas + hydro_manual.filter_status   (run as postgres)
│   ├── 01_filter_bewertung.sql      per-filter base view
│   ├── 02_filter_quality.sql        filter_quality table + enriched view
│   └── 03_optimisation_core.sql     cfg tables + grid + the recommendation views
└── scripts/
    ├── config.py                    single edit point for all parameters
    ├── common_qgis.py               shared QGIS helpers
    ├── 00_stuetzpunkte_aus_konturen.py
    ├── 01_tin_interpolation_absenkung.py
    ├── 02_klassifizierung_raster.py
    ├── 03_polygonisierung_und_aufloesen.py
    ├── 04_rasterzellen_erzeugen.py
    ├── run_steps_00_04.py
    ├── compute_filter_quality.py    per-filter quality metrics -> filter_quality
    └── sync_config_to_db.py         push config.py → cfg_* tables
```

Project working data (`00_Rohdaten`, `01_QGIS_Projekt`, `02_Zwischendaten`,
`03_Ergebnisse`) stays on the network drive and is gitignored.

---

## Setup (once)

1. Copy `.env.example` → `.env`; set `PROJECT_FOLDER` and DB credentials.
2. `sql/00_setup_as_postgres.sql` — run **as `postgres`**.
3. `sql/01_filter_bewertung.sql` — as `geodin2pg_etl_user`.
4. `sql/02_filter_quality.sql` — as `geodin2pg_etl_user`.
5. `sql/03_optimisation_core.sql` — as `geodin2pg_etl_user`.
6. `python scripts/sync_config_to_db.py` — push config into the cfg tables.
7. `python scripts/compute_filter_quality.py` — fill `filter_quality`.

## Run (per horizon)

1. Set `HORIZON` in `scripts/config.py`.
2. Run `scripts/run_steps_00_04.py` in the QGIS Python console → builds
   `gitter_<horizont>` in the GeoPackage.
3. Push the grid to PostGIS (see `scripts/README_pipeline.md`):
   `DELETE FROM gw_analysis.grid_cells WHERE horizon = '<h>';` then import.
4. Load `gw_analysis.v_optimisation_qgis` in QGIS (feature id = `gid`) and
   `gw_analysis.v_gap_cells`; apply styles.

## Re-run after new data

After an ETL refresh of `hydro` (e.g. imported time series), re-run
`python scripts/compute_filter_quality.py` and refresh QGIS. The views
recompute automatically; nothing else changes.

## Change a parameter

Edit `scripts/config.py`, then `python scripts/sync_config_to_db.py`. See the
table at the end of `docs/bewertungslogik_scoring.md` for what lives where.

---

## Status

- [x] Per-filter evaluation view (depth-sign-safe, horizon bands)
- [x] Config-driven core: scoring, grid thinning, gap detection
- [x] Four scoring dimensions incl. data quality & density
- [x] Single comprehensive QGIS layer (`v_optimisation_qgis`)
- [x] Historical time series imported — scoring is now live (records up to ~55 yr)
- [x] User-editable weights, score classes, quality thresholds
- [ ] Combined-abstraction drawdown grid (awaiting modeller contours)
- [ ] Expert grid override (`feature/grid-override`)
- [ ] A3 print-layout template + .qml styles

## Notes

Private repository — client work. No data, credentials, or GeoPackages are
committed. GeoDIN remains the master system and is never modified; `hydro` is a
read-only analytical copy.
