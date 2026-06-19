"""Step 02 - classify the drawdown raster into zones 1..4 (driven by config)."""
import processing
from config import ZWISCHENDATEN, TIN_RASTER_NAME, CLASSIFIED_RASTER_NAME, DRAWDOWN_CLASSES

inp = ZWISCHENDATEN / TIN_RASTER_NAME
out = ZWISCHENDATEN / CLASSIFIED_RASTER_NAME


def build_formula(classes):
    """abs(A) used so the sign of the drawdown value does not matter."""
    parts = []
    for k, c in classes.items():
        lo, hi = c["min_abs"], c["max_abs"]
        if hi is None:
            cond = f"(abs(A) > {lo})"
        elif lo == 0.2:                       # include lower bound for the smallest class
            cond = f"((abs(A) >= {lo}) & (abs(A) <= {hi}))"
        else:
            cond = f"((abs(A) > {lo}) & (abs(A) <= {hi}))"
        parts.append(f"({cond} * {k})")
    return " + ".join(parts)


formula = build_formula(DRAWDOWN_CLASSES)
print(f"EN/DE: classification formula = {formula}")

processing.run("gdal:rastercalculator", {
    "INPUT_A": str(inp), "BAND_A": 1, "FORMULA": formula,
    "NO_DATA": 0, "RTYPE": 0,            # Byte; classes 0-4
    "OPTIONS": "", "EXTRA": "", "OUTPUT": str(out),
})
print(f"EN/DE: step 02 done -> {out}")
