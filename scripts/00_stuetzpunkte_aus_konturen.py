"""Step 00 - extract vertices from the drawdown contour layer."""
import processing
from config import GPKG, INPUT_CONTOUR_LAYER, SUPPORT_POINTS_LAYER
from common_qgis import remove_id_fields, save_layer_to_gpkg

src = f"{GPKG}|layername={INPUT_CONTOUR_LAYER}"

print(f"EN: extract vertices from '{INPUT_CONTOUR_LAYER}' | DE: Stützpunkte extrahieren")
punkte = processing.run("native:extractvertices",
    {"INPUT": src, "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]
punkte = remove_id_fields(punkte)
print(f"EN/DE: {punkte.featureCount()} vertices / Stützpunkte")

save_layer_to_gpkg(punkte, GPKG, SUPPORT_POINTS_LAYER)
print("EN/DE: step 00 done.")
