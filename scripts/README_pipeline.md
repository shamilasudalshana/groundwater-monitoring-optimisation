# Messnetzoptimierung – Pipeline v2 (steps 00–04 + grid push)

## Folder layout (under the project root / .env PROJECT_FOLDER)
```
00_Rohdaten/      raw inputs (drawdown contours, pflichtbereiche) — NOT in git
01_QGIS_Projekt/  the .qgz QGIS project                            — NOT in git
02_Zwischendaten/ intermediate rasters (.tif)                      — NOT in git
03_Ergebnisse/    panzenberg_messnetz_optimierung.gpkg             — NOT in git
docs/             documentation
sql/              the gw_analysis SQL files
scripts/          this folder (config + steps)
```

## Where outputs go
- **One GeoPackage per project**: `03_Ergebnisse/panzenberg_messnetz_optimierung.gpkg`.
- Intermediate rasters: `02_Zwischendaten/*.tif`.
- The grid layer that matters downstream is **`gitter_<horizont>`** (the clean,
  boundary-cleaned grid). The other two grid layers (`gitter_roh_*`,
  `gitter_randzellen_*`) are QA only.

## Setup
1. Copy `.env.example` to `.env` (repo root) and fill in `PROJECT_FOLDER` + DB password.
2. Put the drawdown contours in `00_Rohdaten`, then import them into the GeoPackage
   as `absenkung_<horizont>_konturen` (EPSG:4647). Do the same for `pflichtbereiche`.

## Run (per horizon)
In the QGIS Python console: set `HORIZON` in `config.py`, then run
`run_steps_00_04.py` (or the step files 00→04 in order).
Result: `gitter_<horizont>` in the GeoPackage.

## Push the grid into PostGIS  (gw_analysis.grid_cells)
Do this once per horizon. Robust route via DBeaver + QGIS:

1. QGIS DB Manager → PostGIS → schema `gw_analysis` → Import layer/file →
   input `gitter_oberer`, output table `staging_gitter`, CRS EPSG:4647,
   tick "create spatial index". (Overwrite each run.)
2. In DBeaver:
   ```sql
   INSERT INTO gw_analysis.grid_cells (horizon, drawdown_class, priority, grid_m, geom)
   SELECT 'oberer', klasse, prioritaet, raster_m, ST_Force2D(geom)
   FROM gw_analysis.staging_gitter;
   DROP TABLE gw_analysis.staging_gitter;
   ```

Faster one-liner alternative (OSGeo4W shell), maps columns in one go:
```
ogr2ogr -f PostgreSQL ^
  PG:"host=localhost port=5432 dbname=hydro_db user=geodin2pg_etl_user password=YOURPASS" ^
  -append -nln gw_analysis.grid_cells -nlt POLYGON -t_srs EPSG:4647 -dialect SQLite ^
  -sql "SELECT geom, 'oberer' AS horizon, klasse AS drawdown_class, prioritaet AS priority, raster_m AS grid_m FROM gitter_oberer" ^
  "P:/.../03_Ergebnisse/panzenberg_messnetz_optimierung.gpkg"
```

Pflichtbereiche → `gw_analysis.mandatory_areas` works the same way (columns: horizon, label, geom),
only for horizons where `mandatory_enabled = true`.

## Result
The recommendation is the live PostGIS view `gw_analysis.v_optimisation`
(plus `v_gap_cells`). Load them in QGIS over the PostGIS connection and style.
For a frozen deliverable snapshot, export the filtered view to the GeoPackage as
`optimierung_ergebnis_<horizont>`.
