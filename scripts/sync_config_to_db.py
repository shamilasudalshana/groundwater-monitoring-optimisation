"""
sync_config_to_db.py  -  push config.py values into the gw_analysis.cfg_* tables.

config.py is the single thing you edit. Run this (in your ETL venv, which has
psycopg2) after changing weights / horizons / projects / score classes:

    python sync_config_to_db.py

The cfg_* tables must already exist (run 02_optimisation_core.sql once first).
The views recompute automatically afterwards - just refresh QGIS.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))   # so 'config' imports

import psycopg2
import config as C


def main():
    conn = psycopg2.connect(
        host=C.PG["host"], port=C.PG["port"], dbname=C.PG["dbname"],
        user=C.PG["user"], password=C.PG["password"],
    )
    conn.autocommit = True
    cur = conn.cursor()

    # --- projects ---
    cur.execute("TRUNCATE gw_analysis.cfg_projects;")
    for pid in C.PROJECT_IDS:
        cur.execute("INSERT INTO gw_analysis.cfg_projects (prj_id) VALUES (%s);", (pid,))
    print(f"  cfg_projects     <- {C.PROJECT_IDS}")

    # --- horizons (bands + weights + gap + mandatory) ---
    w = C.SCORING_WEIGHTS
    for hz, (dmin, dmax) in C.HORIZON_BANDS.items():
        cur.execute(
            """
            INSERT INTO gw_analysis.cfg_horizon
                (horizon, depth_min, depth_max,
                 w_timeseries, w_parameter, w_operation,
                 gap_priority_max, mandatory_enabled)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (horizon) DO UPDATE SET
                depth_min = EXCLUDED.depth_min,
                depth_max = EXCLUDED.depth_max,
                w_timeseries = EXCLUDED.w_timeseries,
                w_parameter = EXCLUDED.w_parameter,
                w_operation = EXCLUDED.w_operation,
                gap_priority_max = EXCLUDED.gap_priority_max,
                mandatory_enabled = EXCLUDED.mandatory_enabled;
            """,
            (hz, dmin, dmax, w["timeseries"], w["parameter"], w["operation"],
             C.GAP_PRIORITY_MAX, C.MANDATORY_BY_HORIZON.get(hz, True)),
        )
    print(f"  cfg_horizon      <- {list(C.HORIZON_BANDS)} | weights {w}")

    # --- score classes ---
    cur.execute("TRUNCATE gw_analysis.cfg_score_class;")
    for sc in C.SCORE_CLASSES:
        cur.execute(
            "INSERT INTO gw_analysis.cfg_score_class (min_score, label, decision) VALUES (%s,%s,%s);",
            (sc["min_score"], sc["label"], sc.get("decision")),
        )
    print(f"  cfg_score_class  <- {len(C.SCORE_CLASSES)} classes")

    cur.close()
    conn.close()
    print("done. refresh QGIS to see the recomputed views.")


if __name__ == "__main__":
    main()
