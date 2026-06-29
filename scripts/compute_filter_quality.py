"""
compute_filter_quality.py  -  per-filter time-series quality metrics.

Computes measurement frequency, implausible-jump rate, robust (IQR) outlier
rate, a DETRENDED homogeneity-break flag, and drilling year for every filter
that has groundwater levels, and UPSERTs them into gw_analysis.filter_quality.

Homogeneity note: we remove the linear trend first and test for a step in the
RESIDUALS. A long groundwater trend is informative, not a defect, so testing the
raw series would wrongly flag trending wells. The flag is INFORMATIONAL only
(not part of the score) — a "look at this" signal for the hydrogeologist.

Run in the ETL venv (psycopg2). Pure-Python stats, no numpy needed.
    python compute_filter_quality.py
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import psycopg2
import config as C

QP = getattr(C, "QUALITY_PARAMS", {})
JUMP_THRESH_M = QP.get("jump_threshold_m", 3.0)
JUMP_WINDOW_D = QP.get("jump_window_days", 7)
HOMOG_Z       = QP.get("homogeneity_z", 1.5)
MIN_OUTLIER   = QP.get("min_points_outlier", 8)
MIN_HOMOG     = QP.get("min_points_homogeneity", 20)


def percentile(sv, pct):
    if not sv:
        return None
    if len(sv) == 1:
        return sv[0]
    k = (len(sv) - 1) * pct / 100.0
    lo = int(k); hi = min(lo + 1, len(sv) - 1)
    return sv[lo] + (sv[hi] - sv[lo]) * (k - lo)


def mean(xs):
    return sum(xs) / len(xs)


def pstd(xs):
    if len(xs) < 2:
        return 0.0
    m = mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def metrics(series):
    n = len(series)
    dates = [d for d, _ in series]
    vals  = [v for _, v in series]

    span_days = (dates[-1] - dates[0]).days
    span_years = span_days / 365.25 if span_days > 0 else None
    n_per_year = (n / span_years) if span_years and span_years > 0 else float(n)

    # implausible jumps between near-in-time consecutive readings
    flagged = pairs = 0
    for i in range(1, n):
        dd = (dates[i] - dates[i - 1]).days
        if dd <= JUMP_WINDOW_D:
            pairs += 1
            if abs(vals[i] - vals[i - 1]) > JUMP_THRESH_M:
                flagged += 1
    jump_rate = (flagged / pairs) if pairs > 0 else 0.0

    # robust IQR outliers (informational)
    outlier_rate = None
    if n >= MIN_OUTLIER:
        sv = sorted(vals)
        q1, q3 = percentile(sv, 25), percentile(sv, 75)
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        outlier_rate = sum(1 for v in vals if v < lo or v > hi) / n

    # DETRENDED homogeneity: remove linear trend, test step in residuals
    homog = "insufficient"
    if n >= MIN_HOMOG:
        xs = [(d - dates[0]).days for d in dates]
        mx, my = mean(xs), mean(vals)
        sxx = sum((x - mx) ** 2 for x in xs)
        slope = (sum((xs[i] - mx) * (vals[i] - my) for i in range(n)) / sxx) if sxx > 0 else 0.0
        b = my - slope * mx
        resid = [vals[i] - (slope * xs[i] + b) for i in range(n)]
        half = n // 2
        r1, r2 = resid[:half], resid[half:]
        s = pstd(resid)
        if s > 0 and r1 and r2:
            z = abs(mean(r1) - mean(r2)) / s
            homog = "break_pruefen" if z > HOMOG_Z else "ok"
        else:
            homog = "ok"

    return dict(n_per_year=round(n_per_year, 3), jump_rate=round(jump_rate, 3),
                outlier_rate=None if outlier_rate is None else round(outlier_rate, 3),
                homogeneity_flag=homog, n_used=n)


def main():
    conn = psycopg2.connect(host=C.PG["host"], port=C.PG["port"], dbname=C.PG["dbname"],
                            user=C.PG["user"], password=C.PG["password"])
    cur = conn.cursor()
    cur.execute("""
        SELECT f.filter_id, f.invid, EXTRACT(YEAR FROM st.drilling_end)::int
        FROM hydro.filter f JOIN hydro.station st ON st.station_id = f.station_id
    """)
    info = {fid: (invid, dy) for fid, invid, dy in cur.fetchall()}

    cur.execute("""
        SELECT filter_id, measured_at::date, water_level_m_nn
        FROM hydro.gw_level
        WHERE water_level_m_nn IS NOT NULL AND measured_at IS NOT NULL
        ORDER BY filter_id, measured_at
    """)
    series = {}
    for fid, d, v in cur.fetchall():
        series.setdefault(fid, []).append((d, float(v)))

    rows = 0
    for fid, ser in series.items():
        if fid not in info or len(ser) < 2:
            continue
        invid, dyear = info[fid]
        m = metrics(ser)
        cur.execute("""
            INSERT INTO gw_analysis.filter_quality
                (filter_invid, n_per_year, jump_rate, outlier_rate,
                 homogeneity_flag, drilling_year, n_used, computed_at)
            VALUES (%s,%s,%s,%s,%s,%s,%s, now())
            ON CONFLICT (filter_invid) DO UPDATE SET
                n_per_year=EXCLUDED.n_per_year, jump_rate=EXCLUDED.jump_rate,
                outlier_rate=EXCLUDED.outlier_rate, homogeneity_flag=EXCLUDED.homogeneity_flag,
                drilling_year=EXCLUDED.drilling_year, n_used=EXCLUDED.n_used, computed_at=now();
        """, (invid, m["n_per_year"], m["jump_rate"], m["outlier_rate"],
              m["homogeneity_flag"], dyear, m["n_used"]))
        rows += 1

    conn.commit(); cur.close(); conn.close()
    print(f"filter_quality updated for {rows} filters with data.")


if __name__ == "__main__":
    main()
