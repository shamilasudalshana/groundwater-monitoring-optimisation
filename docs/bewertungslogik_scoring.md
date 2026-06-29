# Scoring & Decision Logic — Messnetzoptimierung

How a filter (well screen) is scored, classified and given a keep/redundant
decision. Every number lives in `sql/03_optimisation_core.sql` (the
`gw_analysis.v_optimisation` view); most are user-editable without touching the
view. This is the reference for understanding and changing it.

---

## 1. The idea in one paragraph

We do **not** invent ideal locations. We take the filters that already exist,
give each a **data-value score (0–100)**, drop them into a **drawdown-scaled
grid**, and within each grid cell keep the best-scored filter (or the mandatory
ones). The drawdown model decides *where* monitoring matters and *how dense* the
grid is; the score decides *which* filter is worth keeping where several compete.
Everything is computed **per horizon** (oberer / mittlerer / tieferer)
independently — see §7.

---

## 2. The total score (four dimensions)

```
score_total = (w_ts·sc_ts + w_param·sc_param + w_qual·sc_quality + w_ops·sc_ops)
              ──────────────────────────────────────────────────────────────────
                            (w_ts + w_param + w_qual + w_ops)
```

- Four sub-scores, each 0–100 (§3–§6).
- Weights read per horizon from `gw_analysis.cfg_horizon`
  (`w_timeseries`, `w_parameter`, `w_quality`, `w_operation`). Default
  0.40 / 0.30 / 0.15 / 0.15. The sum need not be 1 — only the ratio matters.
- Rounded to one decimal, exposed as `score_total`.

**Change the weights:** edit `SCORING_WEIGHTS` in `config.py` → `python
sync_config_to_db.py`, or `UPDATE gw_analysis.cfg_horizon SET ...`.

---

## 3. Sub-score 1 — time series (`sc_ts`)

Rewards a long, continuous record. `0` if the filter has no GW levels. Otherwise
a 60/40 blend of record length and continuity:

| record length (yr) | length_score | | continuity status | continuity_score |
|--------------------|-------------:|-|-------------------|-----------------:|
| ≥ 10 | 100 | | continuous_or_no_major_gap | 100 |
| ≥ 5  | 80  | | minor_gaps    | 70 |
| ≥ 2  | 50  | | major_gaps    | 40 |
| > 0  | 20  | | discontinuous | 20 |
| 0    | 0   | | (other)       | 30 |

`sc_ts = 0.6·length_score + 0.4·continuity_score`. **Change:** `sc_ts` CASE in
the `scored` CTE.

> The historical records are now imported — record lengths run up to ~55 years
> (median ~16). This sub-score is live and differentiating wells.

---

## 4. Sub-score 2 — parameters (`sc_param`)

| has GW level | has water quality | sc_param |
|:---:|:---:|---:|
| yes | yes | 100 |
| yes | no  | 70  |
| no  | yes | 50  |
| no  | no  | 0   |

**Change:** `sc_param` CASE in the `scored` CTE.

---

## 5. Sub-score 3 — data quality & density (`sc_quality`)

Rewards how *densely and cleanly* a well is measured. `0` if no GW levels.
Otherwise a frequency score, minus a capped penalty for implausible jumps:

```
sc_quality = frequency_score − min(30, jump_rate·100)
```

| measurements / year | frequency_score |
|---------------------|----------------:|
| ≥ 12 | 100 |
| ≥ 4  | 75  |
| ≥ 1  | 45  |
| > 0  | 20  |

- **jump_rate** = fraction of near-in-time consecutive readings that jump more
  than the physical threshold (default > 3 m within 7 days) — targets sensor /
  transcription errors, not seasonality.
- **homogeneity_flag is INFORMATIONAL, not scored.** It is detected on the
  *detrended* series (linear trend removed, step tested in the residuals) so it
  flags *artificial* level shifts, not real trends — but a flag still means
  "review," not "penalise." A groundwater trend is informative, not a defect, so
  it must never lower a well's score.
- **outlier_rate** (robust IQR) and **drilling_year** are also informational.

Inputs come from `gw_analysis.filter_quality`, computed by
`scripts/compute_filter_quality.py`. **Change the score:** `sc_quality` CASE in
the `scored` CTE. **Change the thresholds:** `QUALITY_PARAMS` in `config.py`,
then re-run `compute_filter_quality.py`.

---

## 6. Sub-score 4 — operation (`sc_ops`)

From the human-curated `hydro_manual.filter_status` (never overwritten by the
ETL). Dismantled wells are penalised, not dropped.

| operational_status | sc_ops |
|--------------------|-------:|
| aktiv | 100 | unbekannt | 60 |
| stillgelegt | 25 | rueckgebaut | 0 |
| (other) | 60 | | |

**Change the score:** `sc_ops` CASE. **Change the data:** `UPDATE
hydro_manual.filter_status`.

---

## 7. Per-horizon ranking and the decision (`entscheid`)

Each filter is assigned a horizon by mid-depth (`cfg_horizon` bands) and joined
only to grid cells of the **same** horizon. Each grid cell has a unique
`cell_id`, so ranking `PARTITION BY cell_id` is automatically within one horizon
— overlapping cells from different horizons are separate partitions. Within a
cell, order is `is_mandatory ↓, score_total ↓, record_length ↓, n_gw_levels ↓,
n_water_quality ↓, filter_id`.

| entscheid | meaning |
|-----------|---------|
| `pflicht_behalten` | inside a mandatory area → always kept |
| `behalten_beste_im_raster` | 1st choice — best-scored filter in a cell with no mandatory well (kept) |
| `alternative_2` | 2nd-best filter in the cell — fallback if the 1st is unsuitable on review |
| `alternative_3` | 3rd-best filter in the cell |
| `redundant_pruefen` | rank ≥ 4, or any non-mandatory in a cell already covered by a mandatory well → review for removal |
| `ausserhalb_absenkungszone` | outside every grid cell |

`rank_in_cell` carries the full within-cell ordering, so the boss can sort a
crowded cell by it to walk down the list past the 3rd choice if needed.

---

## 8. Score class label (`score_klasse`)

From `gw_analysis.cfg_score_class` (a row applies when `score_total >= min_score`,
highest wins): 75 → sehr gut, 55 → gut, 35 → mittel, 1 → gering, 0 → keine Daten.
**Change:** `SCORE_CLASSES` in `config.py` → sync, or edit `cfg_score_class`.

---

## 9. The single QGIS layer

Load **`gw_analysis.v_optimisation_qgis`** (feature id = `gid`). It carries every
fact, every quality metric (`n_per_year`, `jump_rate`, `homogeneity_flag`,
`outlier_rate`, `drilling_year`), all four sub-scores, the total, the class and
the decision — so there is no need for a second table in QGIS.

---

## 10. Quick map: "I want to change X" → where

| Change… | Where |
|---------|-------|
| Weights (ts / param / quality / ops) | `config.py SCORING_WEIGHTS` → sync, or `cfg_horizon` |
| Score class cutoffs / labels | `config.py SCORE_CLASSES` → sync, or `cfg_score_class` |
| Horizon depth bands | `config.py HORIZON_BANDS` → sync, or `cfg_horizon` |
| Quality thresholds (jump, homogeneity) | `config.py QUALITY_PARAMS` → re-run `compute_filter_quality.py` |
| Gap priority threshold | `config.py GAP_PRIORITY_MAX` → sync, or `cfg_horizon` |
| Mandatory on/off per horizon | `config.py MANDATORY_BY_HORIZON` → sync, or `cfg_horizon` |
| Projects analysed | `config.py PROJECT_IDS` → sync, or `cfg_projects` |
| Grid cell sizes per zone | `config.py DRAWDOWN_CLASSES[grid_m]` → re-run steps 00–04 |
| Sub-score rubric (the bands) | `scored` CTE in `sql/03_optimisation_core.sql` → re-run file |

After any `cfg_*` change the views recompute automatically — just refresh QGIS.
After editing a view file, re-run it. After new GW data, re-run
`compute_filter_quality.py`.
