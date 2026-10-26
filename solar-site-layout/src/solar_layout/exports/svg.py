"""SVG plan.

Page units are millimetres (width/height in mm, viewBox in mm). The plan is a nested
<svg id="plan"> whose viewBox is in site METRES, so drawing millimetres and site metres
never mix: the printed scale is exactly 1:scale. Plan coordinates are

    X = x - x0      Y = y1 - y        (metres; y flipped so frame north points up)

with x0, y1 recorded in <metadata> and as data attributes, so every vertex maps back to
world coordinates exactly. All text lives in the side panel, never over the geometry.
"""

from __future__ import annotations

import json
import math
from typing import IO, Any, Iterable
from xml.sax.saxutils import escape

from ..jsonio import fmt_float

SCALES = [20, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000, 25000, 50000, 100000, 200000]
MAX_PLAN_W_MM = 400.0
MAX_PLAN_H_MM = 270.0
SIDEBAR_W_MM = 105.0
MARGIN_MM = 10.0
SIDE_PANEL_H_MM = 222.0  # height the side panel text needs

STYLE = """
.site{fill:#f3efe4;stroke:#3b3b3b;stroke-width:1.6px;vector-effect:non-scaling-stroke;fill-rule:evenodd}
.admissible{fill:#dcefdc;stroke:#2e7d32;stroke-width:1px;stroke-dasharray:6 3;vector-effect:non-scaling-stroke;fill-rule:evenodd}
.forbidden{fill:#f6d5d5;fill-opacity:.8;stroke:#c62828;stroke-width:.8px;stroke-dasharray:3 2;vector-effect:non-scaling-stroke;fill-rule:evenodd}
.exclusion{fill:#d84343;fill-opacity:.45;stroke:#8e0000;stroke-width:1.2px;vector-effect:non-scaling-stroke;fill-rule:evenodd}
.table{fill:none;stroke:#37474f;stroke-width:.9px;vector-effect:non-scaling-stroke}
.module{fill:#2f5d8a;stroke:#16324f;stroke-width:.35px;vector-effect:non-scaling-stroke}
.panel-text{font-family:'DejaVu Sans',Arial,sans-serif;fill:#1f2a33}
.h1{font-size:4.6px;font-weight:bold}.h2{font-size:3.4px;font-weight:bold}.t{font-size:2.9px}.small{font-size:2.4px;fill:#4a5560}
.frame{fill:none;stroke:#90a4ae;stroke-width:.3}
"""


def choose_scale(extent_w: float, extent_h: float) -> int:
    for s in SCALES:
        if extent_w * 1000.0 / s <= MAX_PLAN_W_MM and extent_h * 1000.0 / s <= MAX_PLAN_H_MM:
            return s
    return SCALES[-1]


def nice_bar_length(scale: int, max_mm: float = 60.0) -> float:
    best = 1.0
    for exp in range(-2, 6):
        for m in (1, 2, 5):
            L = m * 10.0**exp
            if L * 1000.0 / scale <= max_mm:
                best = L
    return best


def _rings(geom: dict[str, Any] | None) -> list[list]:
    if not geom:
        return []
    t = geom["type"]
    if t == "Polygon":
        return [geom["coordinates"]]
    if t == "MultiPolygon":
        return list(geom["coordinates"])
    if t == "GeometryCollection":
        out = []
        for g in geom["geometries"]:
            out.extend(_rings(g))
        return out
    return []


class _Mapper:
    def __init__(self, x0: float, y1: float):
        self.x0 = x0
        self.y1 = y1

    def pt(self, x: float, y: float) -> str:
        return f"{fmt_float(x - self.x0)},{fmt_float(self.y1 - y)}"

    def path(self, polys: list) -> str:
        parts = []
        for poly in polys:
            for ring in poly:
                pts = ring[:-1] if len(ring) > 1 and ring[0] == ring[-1] else ring
                if len(pts) < 3:
                    continue
                parts.append("M" + " L".join(self.pt(p[0], p[1]) for p in pts) + " Z")
        return " ".join(parts)


def write_svg(
    out: IO[str],
    request: dict[str, Any],
    summary: dict[str, Any],
    regions: dict[str, Any],
    tables: Iterable[dict[str, Any]],
    modules: Iterable[dict[str, Any]],
) -> None:
    site_polys = _rings(request["boundary"])
    xs = [p[0] for poly in site_polys for ring in poly for p in ring]
    ys = [p[1] for poly in site_polys for ring in poly for p in ring]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    span = max(maxx - minx, maxy - miny)
    margin = max(0.03 * span, 1.0)
    x0, x1 = minx - margin, maxx + margin
    y0, y1 = miny - margin, maxy + margin
    ew, eh = x1 - x0, y1 - y0
    scale = choose_scale(ew, eh)
    pw, ph = ew * 1000.0 / scale, eh * 1000.0 / scale
    page_w = MARGIN_MM + pw + MARGIN_MM + SIDEBAR_W_MM + MARGIN_MM
    page_h = MARGIN_MM + max(ph, SIDE_PANEL_H_MM) + MARGIN_MM
    mp = _Mapper(x0, y1)
    q = summary["quantities"]
    dims = summary["dimensions"]
    pl = summary["placement"]
    frame = summary["frame"]

    meta = {
        "result_id": summary["result_id"],
        "payload_digest": summary.get("payload_digest"),
        "input_digest": summary["input_digest"],
        "units": "plan viewBox in metres; page in millimetres",
        "world_from_plan": {"x": "X + x0", "y": "y1 - Y", "x0": x0, "y1": y1},
        "scale_denominator": scale,
        "frame": frame,
        "context": "result_only",
    }
    w = out.write
    w('<?xml version="1.0" encoding="UTF-8"?>\n')
    w(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{page_w:.3f}mm" height="{page_h:.3f}mm" '
        f'viewBox="0 0 {page_w:.3f} {page_h:.3f}" data-result-id="{escape(summary["result_id"])}">\n'
    )
    w(f"<title>Site layout {escape(summary['result_id'])}</title>\n")
    w(f"<metadata>{escape(json.dumps(meta, sort_keys=True))}</metadata>\n")
    w(f"<style>{STYLE}</style>\n")
    w(f'<rect x="0" y="0" width="{page_w:.3f}" height="{page_h:.3f}" fill="#ffffff"/>\n')
    w(f'<rect class="frame" x="{MARGIN_MM}" y="{MARGIN_MM}" width="{pw:.3f}" height="{ph:.3f}"/>\n')
    w(
        f'<svg id="plan" x="{MARGIN_MM}" y="{MARGIN_MM}" width="{pw:.6f}" height="{ph:.6f}" '
        f'viewBox="0 0 {fmt_float(ew)} {fmt_float(eh)}" preserveAspectRatio="xMidYMid meet" overflow="hidden" '
        f'data-x0="{fmt_float(x0)}" data-y1="{fmt_float(y1)}" data-scale="{scale}" data-full-viewbox="0 0 {fmt_float(ew)} {fmt_float(eh)}">\n'
    )
    w(f'<g id="layer-site" data-layer="site"><path class="site" d="{mp.path(site_polys)}"/></g>\n')
    adm = _rings(regions.get("admissible_region"))
    w(f'<g id="layer-admissible" data-layer="admissible">{f"<path class=\"admissible\" d=\"{mp.path(adm)}\"/>" if adm else ""}</g>\n')
    forb = _rings(regions.get("forbidden_region"))
    w(f'<g id="layer-keepout" data-layer="keepout">{f"<path class=\"forbidden\" d=\"{mp.path(forb)}\"/>" if forb else ""}</g>\n')
    w('<g id="layer-exclusions" data-layer="exclusions">')
    for ex in request["exclusions"]:
        w(f'<path class="exclusion" data-exclusion-id="{escape(ex["id"])}" d="{mp.path(_rings(ex["geometry"]))}"/>')
    w("</g>\n")
    w('<g id="layer-tables" data-layer="tables">\n')
    for t in tables:
        pts = " ".join(mp.pt(x, y) for x, y in t["footprint_xy_m"])
        w(f'<polygon class="table" data-table-id="{t["table_id"]}" points="{pts}"/>\n')
    w("</g>\n")
    w('<g id="layer-modules" data-layer="modules">\n')
    for m in modules:
        pts = " ".join(mp.pt(c[0], c[1]) for c in m["corners_xyz_m"])
        w(f'<polygon class="module" data-module-id="{m["module_id"]}" points="{pts}"/>\n')
    w("</g>\n")
    w("</svg>\n")

    # ---- side panel (all text) ----------------------------------------------------------
    sx = MARGIN_MM + pw + MARGIN_MM
    y = MARGIN_MM + 5.0
    w(f'<g id="side-panel" class="panel-text" transform="translate({sx:.3f},0)">\n')

    def text(s: str, cls: str = "t", dy: float = 4.2, x: float = 0.0):
        nonlocal y
        w(f'<text x="{x:.2f}" y="{y:.2f}" class="{cls}">{escape(s)}</text>\n')
        y += dy

    name = request.get("name") or "Untitled site"
    text("Solar Studio · site layout", "h1", 6.0)
    words, lines_, cur = name.split(), [], ""
    for word in words:
        if len(cur) + len(word) + 1 > 46 and cur:
            lines_.append(cur)
            cur = word
        else:
            cur = (cur + " " + word).strip()
    lines_.append(cur)
    for k, line in enumerate(lines_[:2]):
        text(line if k == 0 or len(lines_) <= 2 else line[:43] + "...", "h2", 5.0)
    text("Preliminary layout under stated assumptions.", "small", 3.4)
    text("Not a construction approval.", "small", 6.0)

    # north arrow
    ay = y + 2
    w(f'<g id="north-arrow" transform="translate(8,{ay + 10:.2f})">'
      '<polygon points="0,-10 4,4 0,1 -4,4" fill="#1f2a33"/>'
      '<text x="0" y="-12" text-anchor="middle" class="h2">N</text></g>\n')
    w(f'<text x="18" y="{ay + 5:.2f}" class="t">North = frame north (+y)</text>\n')
    w(f'<text x="18" y="{ay + 9.5:.2f}" class="small">No grid convergence applied</text>\n')
    y = ay + 20

    # scale bar
    bar_m = nice_bar_length(scale)
    bar_mm = bar_m * 1000.0 / scale
    w(f'<text id="scale-text" x="0" y="{y:.2f}" class="t" data-scale="{scale}">Scale 1:{scale} (page in mm, plan in metres)</text>\n')
    y += 4.0
    w(f'<g id="scale-bar" data-bar-m="{fmt_float(bar_m)}" data-bar-mm="{bar_mm:.4f}" transform="translate(0,{y:.2f})">')
    half = bar_mm / 2
    w(f'<rect x="0" y="0" width="{half:.4f}" height="2" fill="#1f2a33"/>')
    w(f'<rect x="{half:.4f}" y="0" width="{half:.4f}" height="2" fill="#ffffff" stroke="#1f2a33" stroke-width="0.3"/>')
    w('<text x="0" y="6" class="small">0</text>')
    w(f'<text id="scale-bar-label" x="{bar_mm:.4f}" y="6" class="small" text-anchor="end">{fmt_float(bar_m)} m</text>')
    w("</g>\n")
    y += 12

    # legend
    text("Legend", "h2", 4.6)
    legend = [
        ("site", "Site boundary (holes unfilled)"),
        ("admissible", "Admissible region (setbacks, keepouts)"),
        ("forbidden", "Exclusion keepout zone"),
        ("exclusion", "Exclusion"),
        ("table", "Table envelope (incl. module gaps)"),
        ("module", "Module (gaps shown as gaps)"),
    ]
    for cls, label in legend:
        w(f'<rect x="0" y="{y - 2.6:.2f}" width="7" height="3.4" class="{cls}" style="vector-effect:none;stroke-width:0.3"/>')
        w(f'<text x="9.5" y="{y:.2f}" class="t">{escape(label)}</text>\n')
        y += 4.6
    y += 2

    text("Quantities", "h2", 4.6)
    gcr = q["module_ground_coverage_gross"]
    bcr = q["module_ground_coverage_buildable"]
    lines = [
        f"Tables: {q['table_count']}   Modules: {q['module_count']}",
        f"DC capacity: {q['dc_capacity_kwp']:.3f} kWp ({q['module_count']} x {fmt_float(q['module_power_wp'])} Wp)",
        f"Table W x L: {dims['table_width_W_m']:.3f} x {dims['table_slope_length_L_m']:.3f} m",
        f"Projected depth D: {dims['table_projected_depth_D_m']:.3f} m  Rise H: {dims['table_rise_H_m']:.3f} m",
        f"Tilt {fmt_float(dims['tilt_deg'])} deg, facing {fmt_float(summary['axes']['facing_azimuth_deg'])} deg",
        f"Row pitch {fmt_float(pl['row_pitch_m'])} m (clear gap {pl['clear_row_gap_m']:.3f} m)",
        f"Gross site area: {q['gross_site_area_m2']:.2f} m2",
        f"Buildable area: {q['buildable_area_m2']:.2f} m2",
        f"Module coverage (gross): {'n/a' if gcr is None else f'{gcr:.4f}'}",
        f"Module coverage (buildable): {'n/a' if bcr is None else f'{bcr:.4f}'}",
        f"Placement: {pl['mode']} ({pl['optimality']})",
    ]
    for line in lines:
        text(line, "t", 4.0)
    y += 2
    text("Identity", "h2", 4.6)
    ident = [
        f"Result {summary['result_id']}",
        f"Input digest {summary['input_digest'][:24]}",
        f"Payload digest {str(summary.get('payload_digest', ''))[:24]}",
        "Result-only plan; projects: see context export",
        f"Frame {frame['kind']} '{frame['id']}'" + (f" {frame['crs']}" if frame.get("crs") else ""),
        "Units: metres. x East, y North.",
        "z: relative to synthetic flat datum (not surveyed)",
    ]
    for line in ident:
        text(line[:60], "small", 3.6)
    y += 2
    text("Out of scope: energy yield, strings, inverters,", "small", 3.4)
    text("structure, terrain, piles, compliance.", "small", 3.4)
    w("</g>\n</svg>\n")
