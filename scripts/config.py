"""
config.py  -  single place for all user inputs (v2, boss-aligned pipeline).

Machine-specific paths and DB credentials come from a .env file at the repo
root (never committed). For a normal run you usually edit only section 1.
"""
import os
from pathlib import Path

# --- load .env (no external dependency; works in QGIS Python too) ----------
def _load_env():
    try:
        root = Path(__file__).resolve().parents[1]   # repo root = scripts/..
    except NameError:
        root = Path.cwd()
    env = root / ".env"
    if env.exists():
        for line in env.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))
_load_env()

# ==========================================================================
# 1. USER INPUTS  (the section you normally edit)
# ==========================================================================

# Horizon for this run: 'oberer' | 'mittlerer' | 'tieferer'
HORIZON = "oberer"

# Projects analysed together (hydraulically connected Wasserfassungen)
PROJECT_IDS = ["KDDLHC", "STBLHC"]

# Project root (from .env -> PROJECT_FOLDER)
PROJECT_FOLDER = Path(os.environ.get(
    "PROJECT_FOLDER",
    r"P:/2025/250129_Panzenberg_WF_Messnetzoptimierung_Vorauswahl/40_GIS/44_Scrips/SHe_optimisation_v2"
))

# Input layers (must already be inside the project GeoPackage, EPSG:4647)
INPUT_CONTOUR_LAYER       = f"absenkung_{HORIZON}_konturen"
INPUT_CONTOUR_VALUE_FIELD = "absenkung"
MANDATORY_POLYGON_LAYER   = "pflichtbereiche"

# ==========================================================================
# 2. HORIZON / SCORING CONFIG  (mirror of gw_analysis.cfg_* in PostgreSQL)
# ==========================================================================
HORIZON_BANDS        = {"oberer": (0, 50), "mittlerer": (50, 100), "tieferer": (100, 1000000)}
MANDATORY_BY_HORIZON = {"oberer": True, "mittlerer": False, "tieferer": True}
SCORING_WEIGHTS      = {"timeseries": 0.45, "parameter": 0.35, "operation": 0.20}
GAP_PRIORITY_MAX     = 2

# Score classes: score_total -> label/decision. Edit freely; pushed to
# gw_analysis.cfg_score_class by sync_config_to_db.py. A row applies when
# score_total >= min_score (highest matching min_score wins).
SCORE_CLASSES = [
    {"min_score": 75, "label": "sehr gut",    "decision": "behalten_bevorzugt"},
    {"min_score": 55, "label": "gut",         "decision": "behalten"},
    {"min_score": 35, "label": "mittel",      "decision": "pruefen"},
    {"min_score": 1,  "label": "gering",      "decision": "schwach"},
    {"min_score": 0,  "label": "keine Daten", "decision": "keine_daten"},
]

# ==========================================================================
# 3. DRAWDOWN CLASSES  (zone threshold + grid cell size per zone)  [USER]
#    grid_m = square cell side in metres  ->  this IS the user-defined grid sizing
# ==========================================================================
DRAWDOWN_CLASSES = {
    1: {"label": ">5 m",    "min_abs": 5.0, "max_abs": None, "grid_m": 1000.0, "grid_km2": 1.0,  "priority": 1},
    2: {"label": "2-5 m",   "min_abs": 2.0, "max_abs": 5.0,  "grid_m": 2000.0, "grid_km2": 4.0,  "priority": 2},
    3: {"label": "1-2 m",   "min_abs": 1.0, "max_abs": 2.0,  "grid_m": 4000.0, "grid_km2": 16.0, "priority": 3},
    4: {"label": "0.2-1 m", "min_abs": 0.2, "max_abs": 1.0,  "grid_m": 8000.0, "grid_km2": 64.0, "priority": 4},
}

# Boundary-cell cleaning: drop clipped cells smaller than this fraction of a full cell.
MIN_AREA_RATIO = 0.25

# ==========================================================================
# 4. CRS / INTERPOLATION
# ==========================================================================
CRS_AUTHID     = "EPSG:4647"
TIN_PIXEL_SIZE = 25

# ==========================================================================
# 5. DATABASE  (credentials from .env; used only by the grid push)
# ==========================================================================
PG = {
    "host":     os.environ.get("PGHOST", "localhost"),
    "port":     os.environ.get("PGPORT", "5432"),
    "dbname":   os.environ.get("PGDATABASE", "hydro_db"),
    "user":     os.environ.get("PGUSER", "geodin2pg_etl_user"),
    "password": os.environ.get("PGPASSWORD", ""),
}

# ==========================================================================
# 6. PATHS + AUTO-GENERATED LAYER NAMES  (no need to edit)
# ==========================================================================
GPKG          = PROJECT_FOLDER / "03_Ergebnisse" / "panzenberg_messnetz_optimierung.gpkg"
ZWISCHENDATEN = PROJECT_FOLDER / "02_Zwischendaten"

# make sure output folders exist
for _d in (ZWISCHENDATEN, GPKG.parent):
    try:
        _d.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

SUPPORT_POINTS_LAYER   = f"absenkung_{HORIZON}_stuetzpunkte"
TIN_RASTER_NAME        = f"absenkung_{HORIZON}_raster.tif"
CLASSIFIED_RASTER_NAME = f"absenkung_{HORIZON}_klassifiziert.tif"
DRAWDOWN_ZONES_LAYER   = f"absenkungszonen_{HORIZON}"

RAW_GRID_LAYER              = f"gitter_roh_{HORIZON}"          # QA: all cells + area ratios
OPTIMIZED_GRID_LAYER        = f"gitter_{HORIZON}"             # -> pushed to gw_analysis.grid_cells
REMOVED_BOUNDARY_GRID_LAYER = f"gitter_randzellen_{HORIZON}"  # QA: removed boundary cells

RASTER_SOURCE = "raster"
