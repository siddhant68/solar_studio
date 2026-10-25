"""DXF plan (ezdxf): named layers, closed LWPOLYLINEs, metre units, world coordinates.

Each table and module polyline carries its ID as XDATA (application SOLAR_STUDIO) so the
drawing can be reconciled with the CSV/JSON records.
"""

from __future__ import annotations

from typing import Any, Iterable

import ezdxf
from ezdxf import units

APPID = "SOLAR_STUDIO"
LAYERS = {
    "SITE_BOUNDARY": 7,
    "SITE_HOLES": 8,
    "ADMISSIBLE_REGION": 3,
    "KEEPOUT_ZONES": 1,
    "EXCLUSIONS": 1,
    "TABLES": 8,
    "MODULES": 5,
    "ANNOTATION": 7,
}


def _polys(geom: dict[str, Any] | None) -> list:
    if not geom:
        return []
    if geom["type"] == "Polygon":
        return [geom["coordinates"]]
    if geom["type"] == "MultiPolygon":
        return list(geom["coordinates"])
    if geom["type"] == "GeometryCollection":
        out = []
        for g in geom["geometries"]:
            out.extend(_polys(g))
        return out
    return []


def _ring_pts(ring) -> list[tuple[float, float]]:
    pts = [(float(p[0]), float(p[1])) for p in ring]
    if len(pts) > 1 and pts[0] == pts[-1]:
        pts = pts[:-1]
    return pts


def _fix_ezdxf_markers(doc) -> None:
    """ezdxf records "created/written by ezdxf <version> @ <timestamp>" in a metadata
    dictionary on every write. Replace both markers with the version alone so the same
    immutable result always produces the same DXF bytes."""
    from ezdxf.document import CREATED_BY_EZDXF, WRITTEN_BY_EZDXF

    marker = f"{ezdxf.__version__} (timestamp omitted for reproducible exports)"
    meta = doc.ezdxf_metadata()
    meta[CREATED_BY_EZDXF] = marker
    meta[WRITTEN_BY_EZDXF] = marker
    doc._update_ezdxf_metadata = lambda: None  # instance override: keep the fixed marker


def build_dxf(
    request: dict[str, Any],
    summary: dict[str, Any],
    regions: dict[str, Any],
    tables: Iterable[dict[str, Any]],
    modules: Iterable[dict[str, Any]],
):
    doc = ezdxf.new("R2018", setup=False)
    doc.units = units.M
    doc.header["$INSUNITS"] = 6  # metres
    doc.header["$MEASUREMENT"] = 1  # metric
    doc.header["$LUNITS"] = 2  # decimal
    doc.appids.add(APPID)
    for name, color in LAYERS.items():
        doc.layers.add(name, color=color)
    _fix_ezdxf_markers(doc)
    msp = doc.modelspace()
    for poly in _polys(request["boundary"]):
        msp.add_lwpolyline(_ring_pts(poly[0]), close=True, dxfattribs={"layer": "SITE_BOUNDARY"})
        for hole in poly[1:]:
            msp.add_lwpolyline(_ring_pts(hole), close=True, dxfattribs={"layer": "SITE_HOLES"})
    for poly in _polys(regions.get("admissible_region")):
        for ring in poly:
            msp.add_lwpolyline(_ring_pts(ring), close=True, dxfattribs={"layer": "ADMISSIBLE_REGION"})
    for poly in _polys(regions.get("forbidden_region")):
        for ring in poly:
            msp.add_lwpolyline(_ring_pts(ring), close=True, dxfattribs={"layer": "KEEPOUT_ZONES"})
    for ex in request["exclusions"]:
        for poly in _polys(ex["geometry"]):
            for ring in poly:
                e = msp.add_lwpolyline(_ring_pts(ring), close=True, dxfattribs={"layer": "EXCLUSIONS"})
                e.set_xdata(APPID, [(1000, f"exclusion:{ex['id']}")])
    for t in tables:
        e = msp.add_lwpolyline([(float(x), float(y)) for x, y in t["footprint_xy_m"]], close=True, dxfattribs={"layer": "TABLES"})
        e.set_xdata(APPID, [(1000, t["table_id"])])
    for m in modules:
        e = msp.add_lwpolyline([(float(c[0]), float(c[1])) for c in m["corners_xyz_m"]], close=True, dxfattribs={"layer": "MODULES"})
        e.set_xdata(APPID, [(1000, m["module_id"])])
    xs = [p[0] for poly in _polys(request["boundary"]) for p in poly[0]]
    ys = [p[1] for poly in _polys(request["boundary"]) for p in poly[0]]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    h = max(span / 60.0, 0.2)
    q = summary["quantities"]
    lines = [
        f"Solar Studio site layout {summary['result_id']}",
        f"{q['table_count']} tables, {q['module_count']} modules, {q['dc_capacity_kwp']:.3f} kWp DC",
        f"Frame {summary['frame']['kind']} {summary['frame']['id']}; units m; z relative flat datum",
    ]
    for k, line in enumerate(lines):
        msp.add_text(line, height=h, dxfattribs={"layer": "ANNOTATION", "insert": (min(xs), max(ys) + h * (2 + 1.6 * (len(lines) - k)))})
    return doc
