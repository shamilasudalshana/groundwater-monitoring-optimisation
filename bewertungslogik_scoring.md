# Scoring & Decision Logic — Messnetzoptimierung

How a filter (well screen) is scored, classified and given a keep/redundant
decision. Every number here lives in `sql/02_optimisation_core.sql` (the
`gw_analysis.v_optimisation` view) and most are user-editable without touching
the view. This document is the reference for understanding and changing it.

---

## 1. The idea in one paragraph

We do **not** invent ideal locations. We take the filters that already exist,
give each one a **data-value score (0–100)**, drop them into a **drawdown-scaled
grid**, and within each grid cell keep the best-scored filter (or the mandatory
ones). The drawdown model decides *where* monitoring matters and *how dense* the
grid is; the score decides *which* filter is worth keeping where several compete.
Everything is computed **per horizon** (oberer / mittlerer / tieferer)
independently — see §6.

---

## 2. The total score

```
score_total = (w_ts · sc_ts  +  w_param · sc_param  +  w_ops · sc_ops)
              ────────────────────────────────────────────────────────
                            (w_ts + w_param + w_ops)
```

- `sc_ts`, `sc_param`, `sc_ops` are three sub-scores, each 0–100 (§3–§5).
- `w_ts`, `w_param`, `w_ops` are the **weights**, read per horizon from
  `gw_analysis.cfg_horizon`. Dividing by the weight sum means the weights do not
  need to add up to 1 — only their *ratio* matters.
- Result is rounded to one decimal and exposed as `score_total`.

**To change the weights:** edit `SCORING_WEIGHTS` in `config.py` and run
`python sync_config_to_db.py`, or directly:
```sql
UPDATE gw_analysis.cfg_horizon
SET w_timeseries = 0.50, w_parameter = 0.30, w_operation = 0.20;
```

---

## 3. Sub-score 1 — time series (`sc_ts`)

Rewards a long, continuous, real record. If the filter has **no** groundwater
levels, `sc_ts = 0`. Otherwise it is a 60/40 blend of record length and
continuity:

```
sc_ts = 0.6 · length_score + 0.4 · continuity_score
```

| record length (years) | length_score |
|-----------------------|-------------:|
| ≥ 10                  | 100 |
| ≥ 5                   | 80  |
| ≥ 2                   | 50  |
| > 0                   | 20  |
| 0 / none              | 0   |

| continuity status (`gw_continuity_status`) | continuity_score |
|---------------------------------------------|-----------------:|
| continuous_or_no_major_gap                  | 100 |
| minor_gaps                                  | 70  |
| major_gaps                                  | 40  |
| discontinuous                               | 20  |
| (other / insufficient)                      | 30  |

**To change:** edit the `sc_ts` CASE expressions in the `scored` CTE of
`sql/02_optimisation_core.sql`, then re-run that file. The 0.6 / 0.4 split and
the band breakpoints are the levers here.

> Note for the current Panzenberg data: most filters have no time series yet,
> so `sc_ts = 0` for them today. When the historical records are imported and
> the ETL refreshes `hydro`, this sub-score lights up and rankings sharpen —
> no code change needed.

---

## 4. Sub-score 2 — parameters (`sc_param`)

Rewards what a filter actually measures. A filter that carries both groundwater
levels and water-quality data is worth more than a level-only one.

| has GW level | has water quality | sc_param |
|:------------:|:-----------------:|---------:|
| yes          | yes               | 100 |
| yes          | no                | 70  |
| no           | yes               | 50  |
| no           | no                | 0   |

**To change:** edit the `sc_param` CASE in the `scored` CTE.

---

## 5. Sub-score 3 — operation (`sc_ops`)

Rewards a usable, accessible well. Status comes from the human-curated
`hydro_manual.filter_status` table (joined into `v_filter_bewertung`), so it is
never overwritten by the ETL. Dismantled wells are **penalised, not dropped** —
they stay visible for the reviewer.

| operational_status | sc_ops |
|--------------------|-------:|
| aktiv              | 100 |
| unbekannt          | 60  |
| stillgelegt        | 25  |
| rueckgebaut        | 0   |
| (anything else)    | 60  |

**To change:** edit the `sc_ops` CASE in the `scored` CTE. To change the *data*
(mark a well dismantled etc.), `UPDATE hydro_manual.filter_status`.

---

## 6. Per-horizon ranking and the decision (`entscheid`)

Each filter is assigned a horizon by its mid-depth (`cfg_horizon` bands) and
joined only to grid cells of the **same** horizon. Because every grid cell has a
unique `cell_id`, ranking `PARTITION BY cell_id` is automatically *within one
horizon* — overlapping cells from different horizons are separate partitions.

Within a cell, filters are ordered by:
`is_mandatory ↓, score_total ↓, record_length ↓, n_gw_levels ↓, n_water_quality ↓, filter_id`.

The decision:

| entscheid                  | meaning |
|----------------------------|---------|
| `pflicht_behalten`         | inside a mandatory area (pflichtbereich) → always kept |
| `behalten_beste_im_raster` | best-scored filter in a cell that has no mandatory well |
| `redundant_pruefen`        | another filter already covers this cell → review for removal |
| `ausserhalb_absenkungszone`| outside every grid cell (outside the drawdown area) |

So at one location where all three horizons have a cell, you can see three
`behalten_beste_im_raster` filters — one per horizon.

---

## 7. Score class label (`score_klasse`)

`score_total` is turned into a readable label via `gw_analysis.cfg_score_class`
(a row applies when `score_total >= min_score`, highest match wins):

| min_score | label       | decision (advisory) |
|----------:|-------------|---------------------|
| 75        | sehr gut    | behalten_bevorzugt |
| 55        | gut         | behalten |
| 35        | mittel      | pruefen |
| 1         | gering      | schwach |
| 0         | keine Daten | keine_daten |

**To change:** edit `SCORE_CLASSES` in `config.py` and run the sync, or
`UPDATE`/`INSERT` rows in `gw_analysis.cfg_score_class`.

---

## 8. Quick map: "I want to change X" → where

| Change…                         | Where |
|---------------------------------|-------|
| Weights (ts / param / ops)      | `config.py SCORING_WEIGHTS` → sync, or `cfg_horizon` |
| Score class cutoffs / labels    | `config.py SCORE_CLASSES` → sync, or `cfg_score_class` |
| Horizon depth bands             | `config.py HORIZON_BANDS` → sync, or `cfg_horizon` |
| Gap priority threshold          | `config.py GAP_PRIORITY_MAX` → sync, or `cfg_horizon` |
| Mandatory on/off per horizon    | `config.py MANDATORY_BY_HORIZON` → sync, or `cfg_horizon` |
| Projects analysed               | `config.py PROJECT_IDS` → sync, or `cfg_projects` |
| Grid cell sizes per zone        | `config.py DRAWDOWN_CLASSES[grid_m]` → re-run steps 00–04 |
| Sub-score rubric (the bands)    | `scored` CTE in `sql/02_optimisation_core.sql` → re-run file |

After any `cfg_*` change the views recompute automatically — just refresh QGIS.
After editing the view file, re-run `sql/02_optimisation_core.sql`.
