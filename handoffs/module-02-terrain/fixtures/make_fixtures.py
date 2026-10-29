"""Write the Module 02 terrain fixtures (surfaces and placement cases) with expected values.

    python3 make_fixtures.py          # rewrites surfaces/*.json and cases/*.json

Planning artefact, standard library only. Expected values come from the closed-form
formulas stated in each case (exact rational arithmetic, converted to float at the end);
`check_fixtures.py` re-derives them a second way (barycentric TIN evaluation at the listed
overlay vertices). Neither script is a terrain engine: they evaluate stated formulas at
stated points and generate no placement on their own.

Conventions (see ../CONTRACTS.md): table-local support coordinates (a, d) are metres along
Module 01's u (table width) and v (horizontal up-slope) axes from the table origin. The
first placement policy is a rigid vertical lift: lower-edge elevation
    L = max over the footprint of (G(p) - d(p) * tan(beta)) + minimum_clearance + structure_depth
and every Module 01 z value of that table is raised by (L - lower_edge_height_m).
"""

from __future__ import annotations

import json
import math
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
M01 = HERE.parents[1] / "module-01" / "fixtures"

LOCAL_FRAME = {"kind": "local_cartesian", "id": "local:analytic-site", "units": "m", "axes": {"x": "east", "y": "north"}}
LOCAL_VERTICAL = {"kind": "local", "id": "local:fixture-datum", "crs": None, "units": "m", "positive": "up"}

# Module 01 identities observed for these layout requests at fe15c5f (algorithm
# lattice-fixed-and-phase3x3/1, geom-policy/1). A different Module 01 version gives
# different IDs; the footprints are the contract the fixtures depend on.
LAYOUTS = {
    "rectangle": {
        "request": "../../module-01/fixtures/rectangle.request.json",
        "observed_result_id": "res_410d496155af5459caa61028",
        "observed_payload_digest": "450141e5c44c2d6f9816debfbe96c6369f20efc0b29c85768dc0794827207ffc",
        "tilt_tan": F(0), "lower_edge_height_m": F(4, 5), "W": F(2), "D": F(4), "power_wp": 550, "modules_per_table": 4,
        "tables": {"T_j0_i0": (1, 1), "T_j0_i1": (4, 1), "T_j0_i2": (7, 1), "T_j1_i0": (1, 6), "T_j1_i1": (4, 6), "T_j1_i2": (7, 6)},
    },
    "single-tilted-3-4-5": {
        "request": "layouts/single-tilted-3-4-5.layout-request.json",
        "observed_result_id": "res_927a1bf4f489084fc4e05685",
        "observed_payload_digest": "9b1be5d89497a6519894c92e6125a2e13df9454afdcf1ede6f328adca1086bda",
        "tilt_tan": F(3, 4), "lower_edge_height_m": F(4, 5), "W": F(2), "D": F(4), "power_wp": 550, "modules_per_table": 2,
        "tables": {"T_j0_i0": (2, 2)},
    },
    "single-flat-4x2": {
        "request": "layouts/single-flat-4x2.layout-request.json",
        "observed_result_id": "res_4c0feedc2e9bff7e31ebdefc",
        "observed_payload_digest": "e0eebb4b07ffd1682fe94f2fd98557b0c2305ac256a30740d412332bbf92491e",
        "tilt_tan": F(0), "lower_edge_height_m": F(4, 5), "W": F(4), "D": F(2), "power_wp": 550, "modules_per_table": 4,
        "tables": {"T_j0_i0": (2, 3)},
    },
}


def fl(x: F) -> float:
    return float(x)


def canonical(value) -> str:
    """Module 01's canonical JSON: sorted keys, no whitespace, shortest round-trip floats, -0.0 as 0.0."""
    def canon(v):
        if isinstance(v, float):
            return 0.0 if v == 0.0 else v
        if isinstance(v, dict):
            return {k: canon(x) for k, x in v.items()}
        if isinstance(v, list):
            return [canon(x) for x in v]
        return v
    return json.dumps(canon(value), sort_keys=True, separators=(",", ":"), allow_nan=False)


def terrain_identity(s: dict) -> tuple[str, str]:
    """CONTRACTS.md section 2: digest over frame (crs null when absent), vertical (crs null when absent),
    float vertices and integer triangles; ID = ter_ + sha256('solar.terrain.surface/1|' + digest)[:24]."""
    import hashlib
    frame = dict(s["frame"])
    frame.setdefault("crs", None)
    vertical = dict(s["vertical"])
    vertical.setdefault("crs", None)
    body = {"frame": frame, "vertical": vertical, "vertices_xyz_m": [[float(c) for c in v] for v in s["vertices_xyz_m"]], "triangles": [[int(i) for i in t] for t in s["triangles"]]}
    digest = hashlib.sha256(canonical(body).encode()).hexdigest()
    return digest, "ter_" + hashlib.sha256(("solar.terrain.surface/1|" + digest).encode()).hexdigest()[:24]


def surface(name, vertices, triangles, description, frame=LOCAL_FRAME, vertical=LOCAL_VERTICAL):
    return {
        "schema_version": "solar.terrain.surface/1",
        "name": name,
        "frame": frame,
        "vertical": vertical,
        "source": {"kind": "synthetic_analytic", "description": description},
        "vertices_xyz_m": [[fl(F(x)), fl(F(y)), fl(F(z))] for x, y, z in vertices],
        "triangles": triangles,
    }


def plane_rect(name, x0, y0, x1, y1, z0, gx, gy, description):
    g = lambda x, y: F(z0) + F(gx) * x + F(gy) * y  # noqa: E731
    v = [(x0, y0, g(F(x0), F(y0))), (x1, y0, g(F(x1), F(y0))), (x1, y1, g(F(x1), F(y1))), (x0, y1, g(F(x0), F(y1)))]
    return surface(name, v, [[0, 1, 2], [0, 2, 3]], description)


SURFACES = {
    "plane-rectangle": plane_rect("Plane G = 100 + 0.05 x + 0.10 y over the rectangle site", 0, 0, 12, 14, 100, F(1, 20), F(1, 10),
                                  "Two triangles over [0,12] x [0,14]; G(x, y) = 100 + 0.05 x + 0.10 y"),
    "plane-rectangle-west-half": plane_rect("Same plane, surveyed only for x in [0, 6]", 0, 0, 6, 14, 100, F(1, 20), F(1, 10),
                                            "Two triangles over [0,6] x [0,14]; everything with x > 6 is unknown ground"),
    "plane-north-0p25": plane_rect("Plane G = 50 + 0.25 y", 0, 0, 6, 8, 50, 0, F(1, 4), "Two triangles over [0,6] x [0,8]; G = 50 + 0.25 y (rises north)"),
    "plane-north-0p5": plane_rect("Plane G = 20 + 0.5 y (dyadic slope)", 0, 0, 8, 8, 20, 0, F(1, 2), "Two triangles over [0,8] x [0,8]; G = 20 + 0.5 y; every value in case T13 is exactly representable"),
    "plane-north-0p6": plane_rect("Steep plane G = 20 + 0.6 y", 0, 0, 8, 8, 20, 0, F(3, 5), "Two triangles over [0,8] x [0,8]; G = 20 + 0.6 y (about 31 degrees)"),
    "hill-fan": surface(
        "Fan with a raised centre vertex",
        [(0, 0, 10), (8, 0, 10), (8, 8, 10), (0, 8, 10), (4, 4, F(106, 10))],
        [[0, 1, 4], [1, 2, 4], [2, 3, 4], [3, 0, 4]],
        "Square [0,8]^2 at z = 10 with one interior vertex (4, 4, 10.6); four triangles, CCW",
    ),
    "flat-micro-gap": surface(
        "Flat survey with a 0.000001 m wide unsurveyed strip",
        [(0, 0, 10), (4, 0, 10), (4, 8, 10), (0, 8, 10), (4.000001, 0, 10), (8, 0, 10), (8, 8, 10), (4.000001, 8, 10)],
        [[0, 1, 2], [0, 2, 3], [4, 5, 6], [4, 6, 7]],
        "Two flat rectangles [0,4] x [0,8] and [4.000001,8] x [0,8] at z = 10; the strip between them is not surveyed",
    ),
    "hill-fan-tjunction-consistent": surface(
        "Hill fan with a consistent T-junction",
        [(0, 0, 10), (8, 0, 10), (8, 8, 10), (0, 8, 10), (4, 4, F(106, 10)), (6, 2, F(103, 10))],
        [[0, 1, 4], [1, 2, 5], [5, 2, 4], [2, 3, 4], [3, 0, 4]],
        "hill-fan with vertex (6, 2, 10.3) on edge (8,0)-(4,4); triangle [1,2,4] split into [1,2,5] and [5,2,4]; [0,1,4] keeps the full edge. 10.3 is the edge's interpolated elevation",
    ),
    "hill-fan-tjunction-cracked": surface(
        "Hill fan with a cracked T-junction",
        [(0, 0, 10), (8, 0, 10), (8, 8, 10), (0, 8, 10), (4, 4, F(106, 10)), (6, 2, F(105, 10))],
        [[0, 1, 4], [1, 2, 5], [5, 2, 4], [2, 3, 4], [3, 0, 4]],
        "As the consistent variant but the junction vertex says 10.5 where the edge interpolates to 10.3: two elevations along one line (INVALID_TERRAIN)",
    ),
    "void-ring": surface(
        "Flat ring with an unsurveyed 1 x 1 m hole",
        [(0, 0, 10), (8, 0, 10), (8, 8, 10), (0, 8, 10), (F(7, 2), F(7, 2), 10), (F(9, 2), F(7, 2), 10), (F(9, 2), F(9, 2), 10), (F(7, 2), F(9, 2), 10)],
        [[0, 1, 5], [0, 5, 4], [1, 2, 6], [1, 6, 5], [2, 3, 7], [2, 7, 6], [3, 0, 4], [3, 4, 7]],
        "Square [0,8]^2 at z = 10 without triangles over [3.5,4.5]^2 (a void, not a pit)",
    ),
}


def support_points(W, D, inset_a, ds):
    return [[fl(inset_a), fl(d)] for d in ds] + [[fl(W - inset_a), fl(d)] for d in ds]


def lift_planar(z0, gx, gy, ox, oy, W, D, tan_b, c, s):
    """Closed form for planar ground G = z0 + gx x + gy y and a south-facing table (u = +x,
    v = +y): G(p) - d tan(beta) is linear, so its maximum over the footprint is at a corner."""
    best = None
    for a in (F(0), W):
        for d in (F(0), D):
            val = z0 + gx * (ox + a) + gy * (oy + d) - d * tan_b
            best = val if best is None or val > best else best
    return best + c + s


def case_planar(case_id, title, layout_key, surface_key, z0, gx, gy, c, s, supports, limits, expected_status=None, unknown=(), notes=""):
    lay = LAYOUTS[layout_key]
    W, D, t = lay["W"], lay["D"], lay["tilt_tan"]
    tables = []
    placed_modules = 0
    for tid, (ox, oy) in lay["tables"].items():
        ox, oy = F(ox), F(oy)
        geom = {"origin_xy_m": [fl(ox), fl(oy)], "footprint_xy_m": [[fl(ox), fl(oy)], [fl(ox + W), fl(oy)], [fl(ox + W), fl(oy + D)], [fl(ox), fl(oy + D)]]}
        if tid in unknown:
            tables.append({"table_id": tid, **geom, "status": "unknown_ground", "reasons": ["footprint_not_fully_covered"], "covered_area_m2": 0.0, "uncovered_area_m2": fl(W * D)})
            continue
        L = lift_planar(F(z0), F(gx), F(gy), ox, oy, W, D, t, F(c), F(s))
        G = lambda a, d: F(z0) + F(gx) * (ox + a) + F(gy) * (oy + d)  # noqa: E731
        clear = {(a, d): L + d * t - F(s) - G(a, d) for a in (F(0), W) for d in (F(0), D)}
        sup = []
        for a, d in supports:
            a, d = F(a), F(d)
            top = L + d * t - F(s)
            sup.append({"a_m": fl(a), "d_m": fl(d), "xy_m": [fl(ox + a), fl(oy + d)], "ground_z_m": fl(G(a, d)), "top_z_m": fl(top), "above_ground_m": fl(top - G(a, d))})
        slope = math.degrees(math.atan(math.hypot(gx, gy)))
        reasons = []
        if limits.get("max_ground_slope_deg") is not None and slope > limits["max_ground_slope_deg"]:
            reasons.append("ground_slope_exceeds_limit")
        if limits.get("max_support_above_ground_m") is not None and any(x["above_ground_m"] > limits["max_support_above_ground_m"] for x in sup):
            reasons.append("support_above_ground_exceeds_limit")
        status = "placed" if not reasons else "infeasible"
        if status == "placed":
            placed_modules += lay["modules_per_table"]
        tables.append({
            "table_id": tid,
            **geom,
            "status": status,
            "reasons": reasons,
            "lower_edge_z_m": fl(L),
            "upper_edge_z_m": fl(L + D * t),
            "vertical_lift_m": fl(L - lay["lower_edge_height_m"]),
            "min_clearance_m": fl(min(clear.values())),
            "max_clearance_m": fl(max(clear.values())),
            "max_ground_slope_deg": slope,
            "covered_area_m2": fl(W * D),
            "uncovered_area_m2": 0.0,
            "supports": sup,
        })
    return {
        "case_id": case_id,
        "title": title,
        "layout": {k: lay[k] for k in ("request", "observed_result_id", "observed_payload_digest", "modules_per_table", "power_wp")} | {"table_width_W_m": fl(W), "table_depth_D_m": fl(D), "tan_tilt": fl(t), "lower_edge_height_m": fl(lay["lower_edge_height_m"])},
        "surface": f"../surfaces/{surface_key}.surface.json",
        "placement_request": {
            "schema_version": "solar.terrain.placement.request/1",
            "source_layout": {"result_id": lay["observed_result_id"], "payload_digest": lay["observed_payload_digest"]},
            "terrain": terrain_identity(SURFACES[surface_key])[1],
            "placement": {"policy": "minimum_clearance_vertical_lift", "minimum_clearance_m": fl(F(c)), "structure_depth_m": fl(F(s))},
            "supports": {"model": "explicit_table_local", "points_ad_m": supports},
            "limits": limits,
            "coverage": "mark_unknown_ground",
        },
        "formula": "planar ground G = z0 + gx x + gy y; L = max over footprint corners of (G - d tan(beta)) + c + s; clearance(a, d) = L + d tan(beta) - s - G; support above-ground height = top - ground",
        "plane": {"z0": fl(F(z0)), "gx": fl(F(gx)), "gy": fl(F(gy))},
        "expected": {
            "tables": tables,
            "placed_tables": sum(1 for x in tables if x["status"] == "placed"),
            "placed_modules": placed_modules,
            "placed_dc_kwp": placed_modules * lay["power_wp"] / 1000.0,
        },
        "notes": notes,
    }


def write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=1) + "\n")


def main() -> None:
    for key, s in SURFACES.items():
        write(HERE / "surfaces" / f"{key}.surface.json", s)
    rect_sup = [[0.5, 0.5], [0.5, 3.5], [1.5, 0.5], [1.5, 3.5]]
    cases = []
    cases.append(case_planar("T01", "Planar terrain under the six-table rectangle layout", "rectangle", "plane-rectangle", 100, F(1, 20), F(1, 10), F(1, 2), 0, rect_sup,
                             {"max_ground_slope_deg": 20.0, "max_support_above_ground_m": 2.0},
                             notes="Every table is placed. The highest ground under a table is at its north-east corner; the lowest clearance (0.5 m) is there and the highest (1.0 m) at the south-west corner."))
    cases.append(case_planar("T02", "Tilted 3-4-5 table on ground rising north at 0.25", "single-tilted-3-4-5", "plane-north-0p25", 50, 0, F(1, 4), F(1, 2), 0, [[0.5, 0.5], [0.5, 3.5], [1.5, 0.5], [1.5, 3.5]],
                             {"max_ground_slope_deg": 20.0, "max_support_above_ground_m": 2.5},
                             notes="tan(beta) = 3/4. G - 0.75 d decreases with d, so the front (lower) edge governs: L = 50.5 + 0.5 = 51.0. Module corners: 51.0 at the lower edge, 54.0 at the upper edge. Rear clearance 2.5 m. Ground slope atan(0.25)."))
    cases.append(case_planar("T05", "Partial survey: the eastern column of tables has no ground", "rectangle", "plane-rectangle-west-half", 100, F(1, 20), F(1, 10), F(1, 2), 0, rect_sup,
                             {"max_ground_slope_deg": 20.0, "max_support_above_ground_m": 2.0}, unknown=("T_j0_i2", "T_j1_i2"),
                             notes="Coverage is closed: tables T_j*_i1 end exactly on x = 6, the surveyed edge, and are covered. Tables T_j*_i2 (x in [7, 9]) are unknown ground: not placed, not extrapolated."))
    cases.append(case_planar("T06", "Support above-ground limit makes a table infeasible", "single-flat-4x2", "plane-north-0p6", 20, 0, F(3, 5), F(1, 2), 0, [[0.5, 0.5], [0.5, 1.5], [3.5, 0.5], [3.5, 1.5]],
                             {"max_ground_slope_deg": 35.0, "max_support_above_ground_m": 1.2},
                             notes="L = 20 + 0.6 x 5 + 0.5 = 23.5. Front supports (d = 0.5, y = 3.5) stand 1.4 m above ground > 1.2 m limit; rear supports 0.8 m. Slope 30.96 deg is within 35 deg."))
    cases.append(case_planar("T07", "Ground slope limit makes a table infeasible", "single-flat-4x2", "plane-north-0p6", 20, 0, F(3, 5), F(1, 2), 0, [[0.5, 0.5], [0.5, 1.5], [3.5, 0.5], [3.5, 1.5]],
                             {"max_ground_slope_deg": 25.0, "max_support_above_ground_m": 2.0},
                             notes="atan(0.6) = 30.96 deg > 25 deg; support heights (1.4 m, 0.8 m) are within 2.0 m."))
    cases.append(case_planar("T13", "Support exactly at the height limit is within it", "single-flat-4x2", "plane-north-0p5", 20, 0, F(1, 2), F(1, 2), 0, [[0.5, 0.5], [0.5, 1.5], [3.5, 0.5], [3.5, 1.5]],
                             {"max_ground_slope_deg": 35.0, "max_support_above_ground_m": 1.25},
                             notes="L = 20 + 0.5 x 5 + 0.5 = 23.0; front supports at y = 3.5 stand exactly 1.25 m above ground (all values dyadic, so exact in double). Equality is within the limit: placed. With max_support_above_ground_m = 1.2499999999 the same table is infeasible (support_above_ground_exceeds_limit); the decision is made by the exact band (CONTRACTS.md 4.3)."))
    # T03: hill touching the middle of the table, all corners lower
    hill = {
        "case_id": "T03",
        "title": "Hill under the middle of a flat table; every corner is lower",
        "layout": {k: LAYOUTS["single-flat-4x2"][k] for k in ("request", "observed_result_id", "observed_payload_digest", "modules_per_table", "power_wp")} | {"table_width_W_m": 4.0, "table_depth_D_m": 2.0, "tan_tilt": 0.0, "lower_edge_height_m": 0.8},
        "surface": "../surfaces/hill-fan.surface.json",
        "placement_request": {
            "schema_version": "solar.terrain.placement.request/1",
            "source_layout": {"result_id": LAYOUTS["single-flat-4x2"]["observed_result_id"], "payload_digest": LAYOUTS["single-flat-4x2"]["observed_payload_digest"]},
            "terrain": terrain_identity(SURFACES["hill-fan"])[1],
            "placement": {"policy": "minimum_clearance_vertical_lift", "minimum_clearance_m": 0.5, "structure_depth_m": 0.0},
            "supports": {"model": "explicit_table_local", "points_ad_m": [[0.5, 1.0], [2.0, 1.0], [3.5, 1.0]]},
            "limits": {"max_ground_slope_deg": 20.0, "max_support_above_ground_m": 2.0},
            "coverage": "mark_unknown_ground",
        },
        "formula": "piecewise-linear TIN; G - d tan(beta) is linear on each triangle, so its maximum over the footprint is at an overlay vertex: footprint corners, TIN vertices inside the footprint, and TIN-edge / footprint-edge intersections",
        "overlay_vertices_xy_m": [[2, 3], [6, 3], [6, 5], [2, 5], [4, 4], [3, 3], [5, 5], [5, 3], [3, 5]],
        "expected": {
            "ground_z_at_overlay_vertices_m": {"2,3": 10.3, "6,3": 10.3, "6,5": 10.3, "2,5": 10.3, "4,4": 10.6, "3,3": 10.45, "5,5": 10.45, "5,3": 10.45, "3,5": 10.45},
            "tables": [{
                "table_id": "T_j0_i0", "origin_xy_m": [2.0, 3.0], "footprint_xy_m": [[2.0, 3.0], [6.0, 3.0], [6.0, 5.0], [2.0, 5.0]], "status": "placed", "reasons": [],
                "lower_edge_z_m": 11.1, "upper_edge_z_m": 11.1, "vertical_lift_m": 10.3,
                "min_clearance_m": 0.5, "min_clearance_at_xy_m": [4.0, 4.0], "clearance_at_footprint_corners_m": 0.8,
                "max_ground_slope_deg": math.degrees(math.atan(0.15)),
                "covered_area_m2": 8.0, "uncovered_area_m2": 0.0,
                "supports": [
                    {"a_m": 0.5, "d_m": 1.0, "xy_m": [2.5, 4.0], "ground_z_m": 10.375, "top_z_m": 11.1, "above_ground_m": 0.725},
                    {"a_m": 2.0, "d_m": 1.0, "xy_m": [4.0, 4.0], "ground_z_m": 10.6, "top_z_m": 11.1, "above_ground_m": 0.5},
                    {"a_m": 3.5, "d_m": 1.0, "xy_m": [5.5, 4.0], "ground_z_m": 10.375, "top_z_m": 11.1, "above_ground_m": 0.725},
                ],
            }],
            "placed_tables": 1, "placed_modules": 4, "placed_dc_kwp": 2.2,
        },
        "must_not": {
            "corner_only_lower_edge_z_m": 10.8,
            "why": "Sampling only the four corners (all at 10.3) gives 10.8, which leaves 0.2 m over the 10.6 m hill top: 0.3 m short of the 0.5 m clearance.",
        },
        "notes": "Each fan triangle rises 0.15 m per metre towards (4, 4). The table must be raised for the hill top, not the corners.",
    }
    cases.append(hill)
    void = {
        "case_id": "T04",
        "title": "Unsurveyed void under the middle of a table; every corner is on surveyed ground",
        "layout": {k: LAYOUTS["single-flat-4x2"][k] for k in ("request", "observed_result_id", "observed_payload_digest", "modules_per_table", "power_wp")} | {"table_width_W_m": 4.0, "table_depth_D_m": 2.0, "tan_tilt": 0.0, "lower_edge_height_m": 0.8},
        "surface": "../surfaces/void-ring.surface.json",
        "placement_request": dict(hill["placement_request"], terrain=terrain_identity(SURFACES["void-ring"])[1]),
        "formula": "coverage = union of the TIN triangles (closed); uncovered area = footprint area - area of footprint intersected with the coverage",
        "expected": {
            "tables": [{"table_id": "T_j0_i0", "origin_xy_m": [2.0, 3.0], "footprint_xy_m": [[2.0, 3.0], [6.0, 3.0], [6.0, 5.0], [2.0, 5.0]], "status": "unknown_ground", "reasons": ["footprint_not_fully_covered"], "covered_area_m2": 7.0, "uncovered_area_m2": 1.0, "corners_covered": True}],
            "placed_tables": 0, "placed_modules": 0, "placed_dc_kwp": 0.0,
        },
        "must_not": {"placed_with_lower_edge_z_m": 10.5, "why": "A corner-sampling or interpolate-across-gaps method would place the table at 10.5 m over ground nobody surveyed."},
        "notes": "The hole [3.5, 4.5]^2 lies wholly inside the footprint [2, 6] x [3, 5].",
    }
    cases.append(void)
    errors = {
        "case_id": "T08",
        "title": "Rejected requests (typed errors; nothing stored)",
        "cases": [
            {"name": "frame mismatch", "change": "surface.frame.id = 'local:other-site' for case T03", "expected_error": "FRAME_MISMATCH", "why": "the terrain and the layout must declare the identical horizontal frame; no transformation is attempted"},
            {"name": "vertical datum mismatch", "change": "T09 inputs (surface vertical = orthometric EPSG:5773) with request.expected_vertical = {kind: orthometric, crs: EPSG:5703}", "expected_error": "DATUM_MISMATCH", "why": "no vertical transformation in Module 02 (PROJ falls back to a no-op ballpark transformation offline; see research/library-probes.json)"},
            {"name": "vertical kind mismatch", "change": "T03 (local datum local:fixture-datum) with request.expected_vertical = {kind: local, id: local:other-benchmark}", "expected_error": "DATUM_MISMATCH", "why": "a different local benchmark is a different reference"},
            {"name": "empty expected_vertical", "change": "request.expected_vertical = {}", "expected_error": "INVALID_INPUT", "why": "assertions must be complete"},
            {"name": "partial expected_vertical", "change": "request.expected_vertical = {kind: orthometric}", "expected_error": "INVALID_INPUT", "why": "kind without crs is not a supported assertion"},
            {"name": "matching expected_vertical", "change": "T09 with request.expected_vertical = {kind: orthometric, crs: EPSG:5773}", "expected_error": None, "why": "accepted; result identical to T09 except parameters_digest and placement_id"},
            {"name": "missing vertical datum", "change": "delete surface.vertical", "expected_error": "INVALID_TERRAIN", "why": "elevations without a declared vertical reference are not accepted"},
            {"name": "source mismatch", "change": "request.source_layout.payload_digest = 64 zeros", "expected_error": "SOURCE_MISMATCH", "why": "a placement names the layout by result_id and payload_digest together"},
            {"name": "unknown layout", "change": "request.source_layout.result_id = res_000000000000000000000000", "expected_error": "RESULT_NOT_FOUND", "why": ""},
            {"name": "degenerate triangle", "change": "hill-fan triangle [0, 1, 4] replaced by [0, 1, 1]", "expected_error": "INVALID_TERRAIN", "why": "zero plan area"},
            {"name": "overlapping triangles", "change": "append triangle [0, 1, 2] to hill-fan", "expected_error": "INVALID_TERRAIN", "why": "a 2.5D surface maps each plan point to one elevation"},
            {"name": "clockwise triangle", "change": "hill-fan triangle [0, 1, 4] written as [0, 4, 1]", "expected_error": "INVALID_TERRAIN", "why": "orientation is part of the contract (counter-clockwise in plan)"},
            {"name": "non-finite elevation", "change": "vertex 4 z = NaN", "expected_error": "INVALID_TERRAIN", "why": ""},
            {"name": "duplicate plan vertex", "change": "append vertex (4, 4, 11.0)", "expected_error": "INVALID_TERRAIN", "why": "two elevations at one plan point"},
            {"name": "cracked T-junction", "surface": "surfaces/hill-fan-tjunction-cracked.surface.json", "expected_error": "INVALID_TERRAIN", "why": "the edge (8,0)-(4,4) interpolates to 10.3 at (6, 2) on one side and the junction vertex says 10.5: a crack with two elevations along one line"},
            {"name": "coordinate beyond envelope", "change": "hill-fan vertex 0 x = 20000000", "expected_error": "RESOURCE_LIMIT", "why": "|x| <= 1e7"},
            {"name": "elevation beyond envelope", "change": "hill-fan vertex 4 z = 30000", "expected_error": "RESOURCE_LIMIT", "why": "|z| <= 2e4"},
            {"name": "too many triangles", "change": "a surface with more triangles than the configured limit (tests lower the limit; the T1 limit is 2,000,000)", "expected_error": "RESOURCE_LIMIT", "why": "checked before geometric work"},
            {"name": "placement time limit", "change": "SOLAR_TERRAIN_TIMEOUT_S = 0 for T01", "expected_error": "RESOURCE_LIMIT", "why": "finite time limit; nothing stored"},
            {"name": "unknown terrain", "change": "request.terrain = ter_000000000000000000000000", "expected_error": "TERRAIN_NOT_FOUND", "why": ""},
            {"name": "unsupported support model", "change": "supports = {model: uniform_rows, ...}", "expected_error": "UNSUPPORTED_OPERATION", "why": "generated rows are T2"},
            {"name": "support outside footprint", "change": "supports.points_ad_m = [[4.5, 1.0]] for case T03 (W = 4)", "expected_error": "INVALID_INPUT", "why": "supports are inside the table footprint"},
            {"name": "negative clearance", "change": "placement.minimum_clearance_m = -0.1", "expected_error": "INVALID_INPUT", "why": ""},
            {"name": "unsupported policy", "change": "placement.policy = 'follow_terrain_reorientation'", "expected_error": "UNSUPPORTED_OPERATION", "why": "reorientation is a later, separately approved milestone"},
        ],
    }
    errors["accepted_variants"] = [
        {"name": "consistent T-junction", "surface": "surfaces/hill-fan-tjunction-consistent.surface.json", "expected": "valid surface; see case T12 (T03 placement unchanged, L = 11.1 m)"},
    ]
    cases.append(errors)
    invariance = {
        "case_id": "T09",
        "title": "Translated and rotated survey frame gives the same placement",
        "base_case": "T03",
        "transform": {"rotate_ccw_deg": 30.0, "about_xy_m": [0.0, 0.0], "then_translate_xy_m": [446000.0, 4412000.0], "facing_azimuth_deg_after": 150.0,
                      "frame_after": {"kind": "projected_cartesian", "id": "utm33n", "crs": "EPSG:32633", "units": "m", "axes": {"x": "east", "y": "north"}},
                      "vertical_after": {"kind": "orthometric", "crs": "EPSG:5773", "units": "m", "positive": "up"}},
        "rule": "Apply the transform to the Module 01 boundary and anchor (azimuth A -> A - 30 for a counter-clockwise rotation) and to every TIN vertex (z unchanged).",
        "expected": "Same table and module IDs, status, lower/upper edge elevations, clearances and support heights as T03 (|difference| <= 1e-9 m); plan coordinates equal the transformed T03 coordinates within 1e-6 m.",
    }
    cases.append(invariance)
    # concrete transformed inputs for T09 (floats: the rotation is irrational)
    th = math.radians(invariance["transform"]["rotate_ccw_deg"])
    tx, ty = invariance["transform"]["then_translate_xy_m"]

    def tf(x, y):
        return [math.cos(th) * x - math.sin(th) * y + tx, math.sin(th) * x + math.cos(th) * y + ty]

    lay = json.loads((HERE / LAYOUTS["single-flat-4x2"]["request"]).read_text())
    lay["name"] = "Single flat 4 x 2 table, rotated 30 deg CCW and translated into EPSG:32633"
    lay["frame"] = invariance["transform"]["frame_after"]
    lay["boundary"]["coordinates"] = [[tf(x, y) for x, y in ring] for ring in lay["boundary"]["coordinates"]]
    lay["placement"]["anchor_xy_m"] = tf(*lay["placement"]["anchor_xy_m"])
    lay["table"]["facing_azimuth_deg"] = invariance["transform"]["facing_azimuth_deg_after"]
    write(HERE / "layouts" / "single-flat-4x2-rotated.layout-request.json", lay)
    hill_s = json.loads(json.dumps(SURFACES["hill-fan"]))
    hill_s["name"] = "Hill fan, rotated 30 deg CCW and translated into EPSG:32633"
    hill_s["frame"] = invariance["transform"]["frame_after"]
    hill_s["vertical"] = invariance["transform"]["vertical_after"]
    hill_s["vertices_xyz_m"] = [tf(x, y) + [z] for x, y, z in hill_s["vertices_xyz_m"]]
    write(HERE / "surfaces" / "hill-fan-rotated.surface.json", hill_s)
    invariance["inputs"] = {"layout_request": "layouts/single-flat-4x2-rotated.layout-request.json", "surface": "surfaces/hill-fan-rotated.surface.json",
                            "observed_result_id": "res_a9f1db03663ea4c6e6d10f35",
                            "observed_payload_digest": "3fa089f7d8e9a634808bbf48bc595f20373b018ad1411011e7a0fcdbb2a9b1ef"}
    invariance["expected_footprint_xy_m"] = [tf(x, y) for x, y in ((2, 3), (6, 3), (6, 5), (2, 5))]
    corruption = {
        "case_id": "T10",
        "title": "Corrupted placement outputs the independent verifier must reject",
        "base_case": "T03 (and T01 for multi-table checks)",
        "mutations": [
            {"change": "tables[0].lower_edge_z_m -= 0.3 and every module z of that table -= 0.3", "must_fail": ["clearance"]},
            {"change": "one module corner z += 0.01", "must_fail": ["module_geometry", "payload_integrity"]},
            {"change": "tables[0].min_clearance_m reported as 0.8 (corner value)", "must_fail": ["clearance_report"]},
            {"change": "T04 table reported as placed at 10.5", "must_fail": ["coverage"]},
            {"change": "a support above_ground_m changed by +0.1", "must_fail": ["supports"]},
            {"change": "source payload_digest in the summary replaced", "must_fail": ["source_linkage"]},
            {"change": "a T01 table record's footprint shifted by 0.1 m in x", "must_fail": ["source_linkage"]},
            {"change": "placed_dc_kwp changed while records unchanged", "must_fail": ["totals"]},
            {"change": "vertical.crs in the summary changed", "must_fail": ["datum"]},
            {"change": "table lifted 1 m higher than the minimum (clearance still satisfied)", "must_fail": ["lift_policy"], "why": "the minimum-clearance policy also fixes the lift; extra lift is not this policy's result"},
        ],
    }
    cases.append(corruption)
    gap = F(repr(4.000001)) - 4  # the represented strip width, exactly
    micro = {
        "case_id": "T11",
        "title": "A 0.000001 m unsurveyed strip under a table whose four corners are surveyed",
        "layout": void["layout"],
        "surface": "../surfaces/flat-micro-gap.surface.json",
        "placement_request": dict(hill["placement_request"], terrain=terrain_identity(SURFACES["flat-micro-gap"])[1]),
        "formula": "exact coverage: the strip's boundary edges x = 4 and x = 4.000001 cross the open footprint, so the footprint is not covered, however narrow the strip",
        "expected": {
            "tables": [{"table_id": "T_j0_i0", "origin_xy_m": [2.0, 3.0], "footprint_xy_m": [[2.0, 3.0], [6.0, 3.0], [6.0, 5.0], [2.0, 5.0]], "status": "unknown_ground", "reasons": ["footprint_not_fully_covered"],
                        "covered_area_m2": fl(8 - 2 * gap), "uncovered_area_m2": fl(2 * gap), "corners_covered": True}],
            "placed_tables": 0, "placed_modules": 0, "placed_dc_kwp": 0.0,
        },
        "must_not": {"why": "an area tolerance or corner sampling would call this covered and place the table at 10.5 m"},
        "notes": "uncovered area = 2 x (double(4.000001) - 4) m^2, about 2e-6 m^2; the status is decided topologically, not by the area",
    }
    cases.append(micro)
    tj = json.loads(json.dumps(hill))
    tj["case_id"] = "T12"
    tj["title"] = "Consistent T-junction: the hill-fan with a split triangle gives the T03 placement"
    tj["surface"] = "../surfaces/hill-fan-tjunction-consistent.surface.json"
    tj["placement_request"]["terrain"] = terrain_identity(SURFACES["hill-fan-tjunction-consistent"])[1]
    tj["notes"] = "The junction vertex (6, 2) lies outside the footprint; the split changes no overlay value inside it."
    cases.append(tj)
    for c in cases:
        write(HERE / "cases" / f"{c['case_id']}.json", c)
    write(HERE / "surfaces" / "INDEX.json", {key: dict(zip(("terrain_digest", "terrain_id"), terrain_identity(json.loads((HERE / "surfaces" / f"{key}.surface.json").read_text()))))
                                            for key in sorted(list(SURFACES) + ["hill-fan-rotated"])})
    print("wrote", len(SURFACES), "surfaces and", len(cases), "cases")


if __name__ == "__main__":
    main()
