"""Step 03 - polygonize the classified raster and dissolve into drawdown zones."""
import processing
from config import GPKG, ZWISCHENDATEN, CLASSIFIED_RASTER_NAME, DRAWDOWN_ZONES_LAYER
from common_qgis import remove_id_fields, save_layer_to_gpkg

inp = ZWISCHENDATEN / CLASSIFIED_RASTER_NAME

print("EN/DE: polygonize / Polygonisierung")
poly = processing.run("gdal:polygonize", {
    "INPUT": str(inp), "BAND": 1, "FIELD": "klasse",
    "EIGHT_CONNECTEDNESS": False, "EXTRA": "", "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]

print("EN/DE: dissolve / auflösen")
diss = processing.run("native:dissolve", {
    "INPUT": poly, "FIELD": ["klasse"], "SEPARATE_DISJOINT": True,
    "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]

diss = remove_id_fields(diss)
save_layer_to_gpkg(diss, GPKG, DRAWDOWN_ZONES_LAYER)
print("EN/DE: step 03 done.")
