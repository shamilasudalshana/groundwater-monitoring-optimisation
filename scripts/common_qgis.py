"""Shared QGIS helpers for the optimisation pipeline (steps 00-04)."""
import processing
from qgis.core import QgsProject, QgsVectorFileWriter


def remove_id_fields(layer):
    """Drop leftover fid / ogc_fid columns that block GeoPackage writes."""
    names = [f.name() for f in layer.fields()]
    drop = [n for n in names if n.lower() in ("fid", "ogc_fid")]
    if drop:
        print(f"EN/DE: removing id fields {drop}")
        layer = processing.run("native:deletecolumn",
            {"INPUT": layer, "COLUMN": drop, "OUTPUT": "TEMPORARY_OUTPUT"})["OUTPUT"]
    return layer


def save_layer_to_gpkg(layer, gpkg, layer_name, drop_ids=True):
    """Write a layer into the project GeoPackage (overwriting that layer)."""
    if drop_ids:
        layer = remove_id_fields(layer)
    opts = QgsVectorFileWriter.SaveVectorOptions()
    opts.driverName = "GPKG"
    opts.layerName = layer_name
    opts.actionOnExistingFile = QgsVectorFileWriter.CreateOrOverwriteLayer
    err = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, str(gpkg), QgsProject.instance().transformContext(), opts)
    print(f"EN/DE: saved '{layer_name}' -> {err}")
    return err


def add_fields_if_missing(layer, fields):
    """Add QgsField objects that aren't already present."""
    existing = [f.name() for f in layer.fields()]
    layer.startEditing()
    for f in fields:
        if f.name() not in existing:
            layer.addAttribute(f)
    layer.updateFields()
    layer.commitChanges()
