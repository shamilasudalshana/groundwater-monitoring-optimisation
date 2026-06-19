"""
Step 04 - build the variable grid (cell size per drawdown zone), clean boundary
cells, and save three layers:
    gitter_roh_<h>        QA: every cell + area ratios
    gitter_<h>            the clean grid  -> pushed to gw_analysis.grid_cells
    gitter_randzellen_<h> QA: removed tiny boundary cells
"""
import processing
from qgis.core import QgsField
from PyQt5.QtCore import QVariant
from config import (GPKG, DRAWDOWN_ZONES_LAYER, DRAWDOWN_CLASSES, MIN_AREA_RATIO,
                    RAW_GRID_LAYER, OPTIMIZED_GRID_LAYER, REMOVED_BOUNDARY_GRID_LAYER)
from common_qgis import remove_id_fields, save_layer_to_gpkg, add_fields_if_missing

zones = f"{GPKG}|layername={DRAWDOWN_ZONES_LAYER}"
clipped_layers = []

# --- 1. one grid per drawdown class, clipped to that class's polygons -------
for klasse, cfg in DRAWDOWN_CLASSES.items():
    raster_m = cfg["grid_m"]
    print(f"EN/DE: class {klasse}, grid {raster_m} m")

    kl = processing.run("native:extractbyexpression",
        {"INPUT": zones, "EXPRESSION": f'"klasse" = {klasse}',
         "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]
    if kl.featureCount() == 0:
        print(f"EN/DE: no polygons for class {klasse}, skip")
        continue

    e = kl.extent()
    extent = (f"{e.xMinimum()},{e.xMaximum()},{e.yMinimum()},{e.yMaximum()} "
              f"[{kl.crs().authid()}]")

    grid = processing.run("native:creategrid", {
        "TYPE": 2, "EXTENT": extent, "HSPACING": raster_m, "VSPACING": raster_m,
        "HOVERLAY": 0, "VOVERLAY": 0, "CRS": kl.crs(),
        "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]

    clipped = processing.run("native:clip",
        {"INPUT": grid, "OVERLAY": kl, "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]

    add_fields_if_missing(clipped, [
        QgsField("klasse", QVariant.Int), QgsField("prioritaet", QVariant.Int),
        QgsField("raster_m", QVariant.Double), QgsField("raster_km2", QVariant.Double),
        QgsField("quelle", QVariant.String)])

    clipped.startEditing()
    ik = clipped.fields().indexOf("klasse");     ip = clipped.fields().indexOf("prioritaet")
    irm = clipped.fields().indexOf("raster_m");   ikm = clipped.fields().indexOf("raster_km2")
    iq = clipped.fields().indexOf("quelle")
    for f in clipped.getFeatures():
        f[ik] = klasse; f[ip] = cfg["priority"]; f[irm] = cfg["grid_m"]
        f[ikm] = cfg["grid_km2"]; f[iq] = "raster"
        clipped.updateFeature(f)
    clipped.commitChanges()
    clipped_layers.append(clipped)

# --- 2. merge all class grids ----------------------------------------------
print("EN/DE: merge class grids")
merged = processing.run("native:mergevectorlayers",
    {"LAYERS": clipped_layers, "CRS": None, "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]
merged = remove_id_fields(merged)

# drop creategrid's non-unique 'id' and mergevectorlayers' 'layer'/'path' noise
present = [c for c in ["id", "layer", "path"] if c in [f.name() for f in merged.fields()]]
if present:
    merged = processing.run("native:deletecolumn",
        {"INPUT": merged, "COLUMN": present, "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]

# --- 3. boundary-cell area ratios ------------------------------------------
add_fields_if_missing(merged, [
    QgsField("area_m2", QVariant.Double), QgsField("full_area", QVariant.Double),
    QgsField("area_ratio", QVariant.Double), QgsField("rand_status", QVariant.String),
    QgsField("entf_grund", QVariant.String)])

merged.startEditing()
ia = merged.fields().indexOf("area_m2");   ifu = merged.fields().indexOf("full_area")
ira = merged.fields().indexOf("area_ratio"); ist = merged.fields().indexOf("rand_status")
ire = merged.fields().indexOf("entf_grund")
for f in merged.getFeatures():
    klasse = f["klasse"]
    area = f.geometry().area()
    if klasse in DRAWDOWN_CLASSES:
        full = DRAWDOWN_CLASSES[klasse]["grid_m"] ** 2
        ratio = area / full
    else:
        full = None; ratio = None
    f[ia] = area; f[ifu] = full; f[ira] = ratio
    if ratio is None:
        f[ist] = "unklar_pruefen"; f[ire] = "klasse_unbekannt"
    elif ratio < MIN_AREA_RATIO:
        f[ist] = "entfernen"; f[ire] = "sehr_kleine_randzelle"
    else:
        f[ist] = "behalten"; f[ire] = None
    merged.updateFeature(f)
merged.commitChanges()

# --- 4. split kept / removed -----------------------------------------------
kept = processing.run("native:extractbyexpression",
    {"INPUT": merged, "EXPRESSION": "\"rand_status\" = 'behalten'",
     "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]
removed = processing.run("native:extractbyexpression",
    {"INPUT": merged, "EXPRESSION": "\"rand_status\" = 'entfernen'",
     "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]

# single-part polygons so PostGIS grid_cells (Polygon, 4647) accepts them cleanly
kept = processing.run("native:multiparttosingleparts",
    {"INPUT": kept, "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]

# --- 5. save ----------------------------------------------------------------
save_layer_to_gpkg(merged,  GPKG, RAW_GRID_LAYER)
save_layer_to_gpkg(kept,    GPKG, OPTIMIZED_GRID_LAYER)
save_layer_to_gpkg(removed, GPKG, REMOVED_BOUNDARY_GRID_LAYER)
print("EN/DE: step 04 done.")
