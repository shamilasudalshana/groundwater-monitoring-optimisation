"""Step 01 - linear TIN interpolation of drawdown onto a raster."""
import processing
from qgis.core import QgsVectorLayer
from config import (GPKG, ZWISCHENDATEN, SUPPORT_POINTS_LAYER, TIN_RASTER_NAME,
                    INPUT_CONTOUR_VALUE_FIELD, TIN_PIXEL_SIZE)

src = f"{GPKG}|layername={SUPPORT_POINTS_LAYER}"
out = ZWISCHENDATEN / TIN_RASTER_NAME

pts = QgsVectorLayer(src, SUPPORT_POINTS_LAYER, "ogr")
if not pts.isValid():
    raise Exception("EN: point layer invalid | DE: Punktlayer ungültig")

fi = pts.fields().indexOf(INPUT_CONTOUR_VALUE_FIELD)
if fi == -1:
    raise Exception(f"EN/DE: field '{INPUT_CONTOUR_VALUE_FIELD}' not found / nicht gefunden")

e = pts.extent()
extent = (f"{e.xMinimum()},{e.xMaximum()},{e.yMinimum()},{e.yMaximum()} "
          f"[{pts.crs().authid()}]")
# INTERPOLATION_DATA format: "<source>::~::<type>::~::<value_field_idx>::~::<use_z>"
data = f"{src}::~::0::~::{fi}::~::0"

print(f"EN/DE: TIN interpolation, field '{INPUT_CONTOUR_VALUE_FIELD}' (idx {fi})")
processing.run("qgis:tininterpolation", {
    "INTERPOLATION_DATA": data,
    "METHOD": 0,                 # 0 = linear
    "EXTENT": extent,
    "PIXEL_SIZE": TIN_PIXEL_SIZE,
    "OUTPUT": str(out),
})
print(f"EN/DE: step 01 done -> {out}")
