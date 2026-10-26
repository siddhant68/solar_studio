"""Runtime probes of the libraries a terrain module would build on (planning evidence).

    python library_probes.py OUT.json

Run in an isolated environment with pyproj, scipy, numpy and rasterio installed (versions
are recorded in the output). Every probe asks one question about shipped behaviour that
the Module 02 contracts depend on; nothing here is a terrain engine. Grids for vertical
datums are deliberately NOT installed and PROJ networking stays disabled, as in a
default offline deployment.
"""

from __future__ import annotations

import json
import sys
import tempfile
import warnings
from pathlib import Path

import numpy as np
import pyproj
import rasterio
import scipy
from pyproj import Transformer
from pyproj.transformer import TransformerGroup
from rasterio.transform import from_origin
from scipy.interpolate import LinearNDInterpolator
from scipy.spatial import Delaunay


def probe_vertical_datum() -> dict:
    """Does PROJ silently fall back to a no-op ('ballpark') vertical transformation when the
    geoid grid is missing? WGS 84 ellipsoidal height -> EGM96 height at 52 N, 13 E."""
    out: dict = {"question": "WGS 84 (EPSG:4979) ellipsoidal height to EGM96 height (EPSG:4326+5773) without the geoid grid installed"}
    out["proj_network_enabled"] = pyproj.network.is_network_enabled()
    t = Transformer.from_crs("EPSG:4979", "EPSG:4326+5773", always_xy=True)
    out["default_transformer"] = t.description
    out["default_result_h_for_input_100m"] = t.transform(13.0, 52.0, 100.0, errcheck=True)[2]
    out["default_accuracy_m"] = t.accuracy  # -1 means unknown
    out["description_says_ballpark"] = "ballpark" in t.description.lower()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        tg = TransformerGroup("EPSG:4979", "EPSG:4326+5773", always_xy=True)
    out["transformer_group_warnings"] = [str(w.message)[:200] for w in caught]
    out["available_operations"] = [x.description for x in tg.transformers]
    out["unavailable_operations"] = [op.name for op in tg.unavailable_operations]
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error")
            tb = Transformer.from_crs("EPSG:4979", "EPSG:4326+5773", always_xy=True, only_best=True)
            out["only_best"] = {"constructed": True, "warnings_or_errors": "none (warnings were turned into errors)", "description": tb.description, "h": tb.transform(13.0, 52.0, 100.0, errcheck=True)[2], "accuracy_m": tb.accuracy}
    except Exception as e:  # the outcome is the evidence
        out["only_best"] = {"constructed": False, "error": f"{type(e).__name__}: {e}"[:400]}
    return out


def probe_tin_across_hole() -> dict:
    """Does an automatic Delaunay TIN interpolate across a data gap? Survey points on a
    square ring (no points inside 2 < |x|,|y| < 8 ... i.e. a hole), plane z = 0.1 x."""
    ring = []
    for x in np.arange(0, 11, 1.0):
        for y in np.arange(0, 11, 1.0):
            if not (3 <= x <= 7 and 3 <= y <= 7):
                ring.append((x, y, 0.1 * x))
    pts = np.array(ring)
    tri = Delaunay(pts[:, :2])
    f = LinearNDInterpolator(tri, pts[:, 2])
    return {
        "question": "scipy Delaunay + LinearNDInterpolator over points with an unsurveyed 4 x 4 m interior gap",
        "points": len(pts),
        "triangles": int(tri.simplices.shape[0]),
        "value_at_gap_centre_5_5": float(f(5.0, 5.0)),
        "find_simplex_at_gap_centre": int(tri.find_simplex([[5.0, 5.0]])[0]),
        "value_outside_hull_12_5": None if np.isnan(f(12.0, 5.0)) else float(f(12.0, 5.0)),
        "observation": "the gap is triangulated and interpolated (value is finite); only points outside the convex hull return NaN",
    }


def probe_raster_nodata_and_registration(tmp: Path) -> dict:
    """How does rasterio expose no-data, sample unmasked values and register ESRI ASCII
    grids given by cell centre (XLLCENTER)?"""
    out: dict = {}
    tif = tmp / "dem.tif"
    data = np.array([[10.0, 11.0, 12.0], [10.5, -9999.0, 12.5], [11.0, 12.0, 13.0]], dtype="float32")
    with rasterio.open(tif, "w", driver="GTiff", height=3, width=3, count=1, dtype="float32", crs="EPSG:32633", transform=from_origin(500000.0, 4100003.0, 1.0, 1.0), nodata=-9999.0) as dst:
        dst.write(data, 1)
    with rasterio.open(tif) as src:
        masked = src.read(1, masked=True)
        centre = (500001.5, 4100001.5)  # centre of the middle (no-data) cell
        out["geotiff"] = {
            "nodata": src.nodata,
            "masked_cells": int(masked.mask.sum()),
            "area_or_point": src.tags().get("AREA_OR_POINT"),
            "sample_unmasked_at_nodata_cell": float(next(src.sample([centre]))[0]),
            "sample_masked_at_nodata_cell_is_masked": bool(np.ma.is_masked(next(src.sample([centre], masked=True))[0])),
            "pixel_centre_of_row0_col0": list(src.xy(0, 0)),
        }
    asc = tmp / "grid.asc"
    asc.write_text("ncols 3\nnrows 2\nxllcenter 10\nyllcenter 20\ncellsize 2\nNODATA_value -9999\n1 2 3\n4 5 -9999\n")
    with rasterio.open(asc) as src:
        b = src.bounds
        out["esri_ascii_xllcenter"] = {
            "header": {"ncols": 3, "nrows": 2, "xllcenter": 10, "yllcenter": 20, "cellsize": 2},
            "gdal_bounds": [b.left, b.bottom, b.right, b.top],
            "expected_lower_left_corner": [9.0, 19.0],
            "pvplant_formula_lower_left_corner": [10 - 2 * 3 / 2.0, 20 - 2 * 2 / 2.0],
            "nodata": src.nodata,
            "masked_cells": int(src.read(1, masked=True).mask.sum()),
        }
    return out


def main() -> int:
    out = {
        "authority": "runtime probe of library behaviour (not REA; not a terrain engine)",
        "versions": {"python": sys.version.split()[0], "pyproj": pyproj.__version__, "proj": pyproj.proj_version_str, "scipy": scipy.__version__, "numpy": np.__version__, "rasterio": rasterio.__version__, "gdal": rasterio.__gdal_version__},
        "vertical_datum": probe_vertical_datum(),
        "tin_across_hole": probe_tin_across_hole(),
    }
    with tempfile.TemporaryDirectory() as d:
        out["raster"] = probe_raster_nodata_and_registration(Path(d))
    Path(sys.argv[1]).write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps(out, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
