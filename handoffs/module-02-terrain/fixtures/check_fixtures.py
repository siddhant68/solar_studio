"""Re-derive the expected values in cases/*.json a second way (planning artefact).

    python3 check_fixtures.py

Standard library only. Where make_fixtures.py uses closed-form plane formulas, this script
evaluates the TIN itself: barycentric elevations, exact (Fraction) clipping of the table
footprint against every triangle for coverage, and the overlay vertices of footprint and
triangles (footprint corners, TIN vertices inside it, edge/edge intersections), where a
piecewise-linear difference attains its extremes. It checks numbers stated in the fixtures;
it produces no placement result and is not the Module 02 engine. Exit status 1 on any
mismatch.
"""

from __future__ import annotations

import json
import math
import sys
from fractions import Fraction as F
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOL = 1e-9
problems: list[str] = []


def fr(x) -> F:
    return F(repr(float(x))) if not isinstance(x, F) else x


def close(a, b, tol=TOL) -> bool:
    return abs(float(a) - float(b)) <= tol


def expect(cond: bool, msg: str) -> None:
    if not cond:
        problems.append(msg)


def load_surface(rel: str) -> dict:
    s = json.loads((HERE / rel).read_text())
    verts = [tuple(fr(c) for c in v) for v in s["vertices_xyz_m"]]
    tris = []
    for i, j, k in s["triangles"]:
        a, b, c = verts[i], verts[j], verts[k]
        area2 = (b[0] - a[0]) * (c[1] - a[1]) - (c[0] - a[0]) * (b[1] - a[1])
        expect(area2 > 0, f"{rel}: triangle {[i, j, k]} is not counter-clockwise with positive area")
        tris.append((a, b, c))
    return {"tris": tris, "verts": verts, "frame": s["frame"], "vertical": s["vertical"]}


def bary(tri, p):
    (x1, y1, _), (x2, y2, _), (x3, y3, _) = tri
    det = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    l1 = ((y2 - y3) * (p[0] - x3) + (x3 - x2) * (p[1] - y3)) / det
    l2 = ((y3 - y1) * (p[0] - x3) + (x1 - x3) * (p[1] - y3)) / det
    return l1, l2, 1 - l1 - l2


def ground(surf, p):
    for tri in surf["tris"]:
        l1, l2, l3 = bary(tri, p)
        if l1 >= 0 and l2 >= 0 and l3 >= 0:
            return l1 * tri[0][2] + l2 * tri[1][2] + l3 * tri[2][2]
    return None


def clip(poly, a, b):
    """Sutherland-Hodgman: keep the part of convex `poly` left of directed edge a->b."""
    out = []
    side = lambda p: (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0])  # noqa: E731
    for i, p in enumerate(poly):
        q = poly[(i + 1) % len(poly)]
        sp, sq = side(p), side(q)
        if sp >= 0:
            out.append(p)
        if (sp >= 0) != (sq >= 0):
            t = sp / (sp - sq)
            out.append((p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1])))
    return out


def area(poly) -> F:
    return abs(sum(poly[i][0] * poly[(i + 1) % len(poly)][1] - poly[(i + 1) % len(poly)][0] * poly[i][1] for i in range(len(poly)))) / 2 if len(poly) >= 3 else F(0)


def seg_intersections(p, q, r, s):
    d = (q[0] - p[0]) * (s[1] - r[1]) - (q[1] - p[1]) * (s[0] - r[0])
    if d == 0:
        return []
    t = ((r[0] - p[0]) * (s[1] - r[1]) - (r[1] - p[1]) * (s[0] - r[0])) / d
    u = ((r[0] - p[0]) * (q[1] - p[1]) - (r[1] - p[1]) * (q[0] - p[0])) / d
    return [(p[0] + t * (q[0] - p[0]), p[1] + t * (q[1] - p[1]))] if 0 <= t <= 1 and 0 <= u <= 1 else []


def inside_rect(fp, p) -> bool:
    return all(((fp[(i + 1) % 4][0] - fp[i][0]) * (p[1] - fp[i][1]) - (fp[(i + 1) % 4][1] - fp[i][1]) * (p[0] - fp[i][0])) >= 0 for i in range(4))


def overlay(surf, fp):
    pts = list(fp)
    pts += [(v[0], v[1]) for v in surf["verts"] if inside_rect(fp, (v[0], v[1]))]
    for tri in surf["tris"]:
        for i in range(3):
            a, b = tri[i][:2], tri[(i + 1) % 3][:2]
            for k in range(4):
                pts += seg_intersections(a, b, fp[k], fp[(k + 1) % 4])
    return sorted(set(pts))


def slope_deg(tri) -> float:
    (x1, y1, z1), (x2, y2, z2), (x3, y3, z3) = tri
    det = (x2 - x1) * (y3 - y1) - (x3 - x1) * (y2 - y1)
    gx = ((z2 - z1) * (y3 - y1) - (z3 - z1) * (y2 - y1)) / det
    gy = ((x2 - x1) * (z3 - z1) - (x3 - x1) * (z2 - z1)) / det
    return math.degrees(math.atan(math.hypot(float(gx), float(gy))))


def check_table(case_id, surf, layout, req, t):
    fp = [tuple(fr(c) for c in p) for p in t["footprint_xy_m"]]
    D = fr(layout["table_depth_D_m"])
    v = ((fp[3][0] - fp[0][0]) / D, (fp[3][1] - fp[0][1]) / D)
    d_of = lambda p: (p[0] - fp[0][0]) * v[0] + (p[1] - fp[0][1]) * v[1]  # noqa: E731
    tanb = fr(layout["tan_tilt"])
    c = fr(req["placement"]["minimum_clearance_m"])
    s = fr(req["placement"]["structure_depth_m"])
    covered = sum((area(clipped) for clipped in (_clip_tri(fp, tri) for tri in surf["tris"])), F(0))
    total = area(fp)
    expect(close(covered, t["covered_area_m2"]) and close(total - covered, t["uncovered_area_m2"]), f"{case_id} {t['table_id']}: coverage {float(covered)}/{float(total)}")
    if t["status"] == "unknown_ground":
        expect(covered < total, f"{case_id} {t['table_id']}: unknown_ground but fully covered")
        if t.get("corners_covered"):
            expect(all(ground(surf, p) is not None for p in fp), f"{case_id}: corners should be covered")
        return None
    pts = overlay(surf, fp)
    vals = [(ground(surf, p), p) for p in pts]
    expect(all(g is not None for g, _ in vals), f"{case_id} {t['table_id']}: overlay vertex without ground")
    L = max(g - d_of(p) * tanb for g, p in vals) + c + s
    expect(close(L, t["lower_edge_z_m"]), f"{case_id} {t['table_id']}: lower edge {float(L)} != {t['lower_edge_z_m']}")
    expect(close(L + D * tanb, t["upper_edge_z_m"]), f"{case_id} {t['table_id']}: upper edge")
    expect(close(L - fr(layout["lower_edge_height_m"]), t["vertical_lift_m"]), f"{case_id} {t['table_id']}: vertical lift")
    clear = [(L + d_of(p) * tanb - s - g, p) for g, p in vals]
    expect(close(min(cl for cl, _ in clear), t["min_clearance_m"]), f"{case_id} {t['table_id']}: min clearance")
    if "max_clearance_m" in t:
        expect(close(max(cl for cl, _ in clear), t["max_clearance_m"]), f"{case_id} {t['table_id']}: max clearance")
    if "min_clearance_at_xy_m" in t:
        at = [p for cl, p in clear if cl == min(x for x, _ in clear)]
        expect([float(at[0][0]), float(at[0][1])] == t["min_clearance_at_xy_m"] and len(at) == 1, f"{case_id}: min clearance location {at}")
    sl = max(slope_deg(tri) for tri in surf["tris"] if area(_clip_tri(fp, tri)) > 0)
    expect(close(sl, t["max_ground_slope_deg"], 1e-9), f"{case_id} {t['table_id']}: slope {sl}")
    for sp in t["supports"]:
        a, d = fr(sp["a_m"]), fr(sp["d_m"])
        u = ((fp[1][0] - fp[0][0]) / fr(layout["table_width_W_m"]), (fp[1][1] - fp[0][1]) / fr(layout["table_width_W_m"]))
        xy = (fp[0][0] + a * u[0] + d * v[0], fp[0][1] + a * u[1] + d * v[1])
        g = ground(surf, xy)
        top = L + d * tanb - s
        expect(close(xy[0], sp["xy_m"][0]) and close(xy[1], sp["xy_m"][1]), f"{case_id}: support xy")
        expect(close(g, sp["ground_z_m"]) and close(top, sp["top_z_m"]) and close(top - g, sp["above_ground_m"]), f"{case_id}: support {sp}")
    lim = req["limits"]
    reasons = []
    if sl > lim["max_ground_slope_deg"]:
        reasons.append("ground_slope_exceeds_limit")
    if any(sp["above_ground_m"] > lim["max_support_above_ground_m"] for sp in t["supports"]):
        reasons.append("support_above_ground_exceeds_limit")
    expect(reasons == t["reasons"] and t["status"] == ("placed" if not reasons else "infeasible"), f"{case_id} {t['table_id']}: status/reasons {reasons}")
    return L, vals


def _clip_tri(fp, tri):
    poly = list(fp)
    a, b, c = (tuple(x[:2]) for x in tri)
    for e0, e1 in ((a, b), (b, c), (c, a)):
        poly = clip(poly, e0, e1)
        if not poly:
            break
    return poly


def main() -> int:
    cases = {p.stem: json.loads(p.read_text()) for p in sorted((HERE / "cases").glob("T*.json"))}
    checked = 0
    for cid, case in cases.items():
        if "placement_request" not in case:
            continue
        surf = load_surface(case["surface"][3:] if case["surface"].startswith("../") else case["surface"])
        last = None
        for t in case["expected"]["tables"]:
            last = check_table(cid, surf, case["layout"], case["placement_request"], t)
            checked += 1
        placed = [t for t in case["expected"]["tables"] if t["status"] == "placed"]
        expect(case["expected"]["placed_tables"] == len(placed), f"{cid}: placed table count")
        expect(case["expected"]["placed_modules"] == len(placed) * case["layout"]["modules_per_table"], f"{cid}: placed modules")
        expect(close(case["expected"]["placed_dc_kwp"], case["expected"]["placed_modules"] * case["layout"]["power_wp"] / 1000), f"{cid}: placed kWp")
        if "ground_z_at_overlay_vertices_m" in case["expected"]:
            for key, z in case["expected"]["ground_z_at_overlay_vertices_m"].items():
                x, y = (fr(v) for v in key.split(","))
                expect(close(ground(surf, (x, y)), z), f"{cid}: ground at {key}")
        if "corner_only_lower_edge_z_m" in case.get("must_not", {}) and last is not None:
            fp = [tuple(fr(c) for c in p) for p in case["expected"]["tables"][0]["footprint_xy_m"]]
            corner_only = max(ground(surf, p) for p in fp) + fr(case["placement_request"]["placement"]["minimum_clearance_m"])
            expect(close(corner_only, case["must_not"]["corner_only_lower_edge_z_m"]) and not close(corner_only, last[0]), f"{cid}: corner-only counterexample")
    # T09: the rotated, translated copy of T03 gives the same elevations
    t09, t03 = cases["T09"], cases["T03"]
    surf = load_surface(t09["inputs"]["surface"])
    table = dict(t03["expected"]["tables"][0], footprint_xy_m=t09["expected_footprint_xy_m"])
    support_xy = []
    th = math.radians(t09["transform"]["rotate_ccw_deg"])
    tx, ty = t09["transform"]["then_translate_xy_m"]
    for sp in table["supports"]:
        x, y = sp["xy_m"]
        support_xy.append(dict(sp, xy_m=[math.cos(th) * x - math.sin(th) * y + tx, math.sin(th) * x + math.cos(th) * y + ty]))
    table["supports"] = support_xy
    table.pop("min_clearance_at_xy_m")
    global TOL
    TOL = 1e-6  # plan coordinates after an irrational rotation; elevations are compared below at 1e-9
    res = check_table("T09", surf, t03["layout"], t03["placement_request"], table)
    TOL = 1e-9
    expect(res is not None and close(res[0], t03["expected"]["tables"][0]["lower_edge_z_m"]), "T09: lower edge differs from T03")
    checked += 1
    if problems:
        print("FAIL")
        for p in problems:
            print(" -", p)
        return 1
    print(f"OK: {checked} table expectations in {len(cases)} cases re-derived from the TINs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
