"""Run steps 00-04 in order from the QGIS Python console."""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))   # so 'config' and 'common_qgis' import

STEPS = [
    "00_stuetzpunkte_aus_konturen.py",
    "01_tin_interpolation_absenkung.py",
    "02_klassifizierung_raster.py",
    "03_polygonisierung_und_aufloesen.py",
    "04_rasterzellen_erzeugen.py",
]

for name in STEPS:
    print(f"\n========== {name} ==========")
    exec(open(HERE / name, encoding="utf-8").read())

print("\nEN/DE: steps 00-04 complete.")
