"""Calculation report (Markdown).

Reproduces the table dimensions, the count x power arithmetic, the area definitions and
denominators, and states the relative-height and limited-pitch assumptions. It invents no
energy, electrical or structural outputs.
"""

from __future__ import annotations

from typing import IO, Any

from ..jsonio import fmt_float


def _r(x: float | None, nd: int = 6) -> str:
    if x is None:
        return "null (denominator is zero)"
    return f"{x:.{nd}f}".rstrip("0").rstrip(".") if isinstance(x, float) else str(x)


def write_report(out: IO[str], request: dict[str, Any], summary: dict[str, Any], provenance: dict[str, Any], sources: list[dict[str, Any]]) -> None:
    q = summary["quantities"]
    d = summary["dimensions"]
    pl = summary["placement"]
    ax = summary["axes"]
    m = request["module"]
    t = request["table"]
    w = out.write
    w(f"# Calculation report — {summary['result_id']}\n\n")
    w("Preliminary flat-site layout under the stated assumptions. It is not a construction approval, and the bounded lattice search is not a claim of a globally optimal plant design.\n\n")
    w("## Identity\n\n")
    w(f"- Result ID: `{summary['result_id']}`\n- Input digest: `{summary['input_digest']}`\n- Numerical payload digest: `{summary.get('payload_digest')}`\n")
    if sources:
        for s in sources:
            w(f"- Source: project `{s['project_id']}` revision {s['project_revision']} (via {s['interface']})\n")
    else:
        w("- Source: direct request (no project)\n")
    w(f"- Algorithm `{provenance['algorithm_version']}`, geometry policy `{provenance['geometry_policy_version']}`, source commit `{provenance.get('source_commit')}`\n\n")

    w("## Frame and site\n\n")
    fr = summary["frame"]
    w(f"- Frame: `{fr['kind']}` id `{fr['id']}`" + (f", CRS `{fr['crs']}` (retained; no transformation performed)" if fr.get("crs") else "") + "\n")
    w("- Units: metres; x East, y North (frame north; no grid convergence correction).\n")
    cf = summary["computation_frame"]
    w(f"- Computation frame: world translated by the anchor {cf['origin_world_xy_m']} ({cf['forward']}); no rotation or scaling of the site.\n")
    w(f"- Perimeter setback: {fmt_float(request['perimeter_setback_m'])} m from every boundary ring (outer rings and holes).\n")
    if request["exclusions"]:
        for ex in request["exclusions"]:
            w(f"- Exclusion `{ex['id']}` with keepout {fmt_float(ex['keepout_m'])} m (true minimum distance).\n")
    else:
        w("- Exclusions: none.\n")
    w("\n## Table dimensions\n\n")
    w(f"Module `{m['model_id']}`: supplied width {fmt_float(m['width_m'])} m (short side), length {fmt_float(m['length_m'])} m, {fmt_float(m['power_wp'])} Wp, orientation **{m['orientation']}**.\n\n")
    w(f"Oriented module: w = {fmt_float(d['module_w_across_m'])} m across the table, l = {fmt_float(d['module_l_upslope_m'])} m up the slope"
      + (" (landscape swaps the supplied sides)" if m["orientation"] == "landscape" else "") + ".\n\n")
    w("| Quantity | Formula | Value |\n|---|---|---|\n")
    w(f"| Table width W | columns·w + (columns−1)·gap_x = {t['columns']}·{fmt_float(d['module_w_across_m'])} + {t['columns'] - 1}·{fmt_float(t['module_gap_x_m'])} | {_r(d['table_width_W_m'])} m |\n")
    w(f"| Slope length L | rows·l + (rows−1)·gap_y = {t['rows']}·{fmt_float(d['module_l_upslope_m'])} + {t['rows'] - 1}·{fmt_float(t['module_gap_y_m'])} | {_r(d['table_slope_length_L_m'])} m |\n")
    w(f"| Projected depth D | L·cos(β), β = {fmt_float(t['tilt_deg'])}° | {_r(d['table_projected_depth_D_m'])} m |\n")
    w(f"| Total rise H | L·sin(β) | {_r(d['table_rise_H_m'])} m |\n")
    w(f"| Lower / upper edge height | lower_edge_height, + H | {_r(d['lower_edge_height_m'])} / {_r(d['upper_edge_height_m'])} m |\n\n")
    w(f"Axes for facing azimuth A = {fmt_float(ax['facing_azimuth_deg'])}° (clockwise from frame north): u = {ax['u_table_width_axis']}, v = {ax['v_uphill_axis']} "
      "(u = (−cos A, sin A), v = (−sin A, −cos A)). Module gaps are measured in the table plane and are not part of any module.\n\n")

    w("## Placement\n\n")
    w(f"- Mode: `{pl['mode']}`; optimality label: `{pl['optimality']}`.\n")
    w(f"- Anchor (world): {pl['anchor_xy_m']}. Candidate origins o(i,j) = anchor + phase + i·(W + table_gap)·u + j·row_pitch·v.\n")
    w(f"- Along-width period W + table_gap = {_r(pl['lattice_period_u_m'])} m; row pitch (lower edge to lower edge) = {fmt_float(pl['row_pitch_m'])} m.\n")
    w(f"- Clear row gap = pitch − D = {_r(pl['clear_row_gap_m'])} m (required minimum {fmt_float(pl['minimum_clear_row_gap_m'])} m).\n")
    w("- A table is kept only if its complete footprint is covered by the site, keeps the setback and every keepout; whole tables are dropped, modules are never cut.\n")
    if pl["mode"] == "phase_search_3x3":
        w(f"- Search scope: {pl['search_scope']}. Objective: {pl['objective']}. Tie-break: {pl['tie_break']}.\n\n")
        w("| Phase (p,q) | Offset u (m) | Offset v (m) | Tables | Modules |\n|---|---|---|---|---|\n")
        for ph in pl["phase_candidates"]:
            mark = " **selected**" if ph["phase_index"] == pl["selected_phase_index"] else ""
            w(f"| ({ph['phase_index'][0]},{ph['phase_index'][1]}){mark} | {_r(ph['offset_u_m'])} | {_r(ph['offset_v_m'])} | {ph['table_count']} | {ph['module_count']} |\n")
    w("\n## Counts and capacity\n\n")
    w(f"- module_count = table_count × rows × columns = {q['table_count']} × {t['rows']} × {t['columns']} = **{q['module_count']}**\n")
    w(f"- dc_capacity_kwp = module_count × module_power_wp / 1000 = {q['module_count']} × {fmt_float(q['module_power_wp'])} / 1000 = **{_r(q['dc_capacity_kwp'], 6)} kWp**\n")
    w("- The supplied nameplate power is the only electrical rating used. No AC capacity, voltage, current, string or inverter value is inferred.\n\n")
    w("## Areas\n\n| Quantity | Definition | Value (m²) |\n|---|---|---|\n")
    w(f"| Physical module area | module_count × supplied width × supplied length = {q['module_count']} × {fmt_float(m['width_m'])} × {fmt_float(m['length_m'])} | {_r(q['physical_module_area_m2'])} |\n")
    w(f"| Projected module area | physical × cos β | {_r(q['projected_module_area_m2'])} |\n")
    w(f"| Table footprint area | table_count × W × D (envelope, includes module gaps) | {_r(q['table_footprint_area_m2'])} |\n")
    w(f"| Gross site area | area of the original polygon(s), holes subtracted | {_r(q['gross_site_area_m2'])} |\n")
    w(f"| Outer-ring area | area inside outer rings, holes not subtracted (reference only) | {_r(q['outer_ring_area_m2'])} |\n")
    lo, hi = q["buildable_area_bounds_m2"]
    w(f"| Buildable area | area of the admissible region after setback and keepouts | {_r(q['buildable_area_m2'])} (bounds {_r(lo)} – {_r(hi)}) |\n\n")
    w(f"- Module ground coverage (gross) = projected module area / gross site area = {_r(q['module_ground_coverage_gross'], 9)}\n")
    w(f"- Module ground coverage (buildable) = projected module area / buildable area = {_r(q['module_ground_coverage_buildable'], 9)}\n")
    w("- Buildable-area bounds: arcs of the setback/keepout offsets are polygonized; the lower bound uses polygons lying outside the true arcs, the upper bound chords on the arcs. Placement decisions never use this polygon: they use exact distances to the original geometry.\n\n")

    w("## Heights\n\n")
    w(f"`z_kind = {summary['z_kind']}`: {summary['z_reference']}. Module corners: z = lower_edge_height + b·sin β where b is the in-plane distance from the lower edge. These are synthetic relative heights, not surveyed elevations or terrain-fitted rack planes.\n\n")
    w("## Row pitch\n\n")
    w("The row pitch above was supplied by the user and checked only for physical overlap (pitch ≥ D) and the requested minimum clear gap (pitch ≥ D + gap). "
      "The separate 2D row-spacing estimate at a specified solar elevation (operation `calculate_row_pitch`) assumes flat ground, equal lower-edge heights, infinitely long rows and direct sun perpendicular to the rows from the facing side: "
      "recommended pitch = max(D + gap, D + H / tan α). It is not an all-year shading guarantee, an obstacle shading model or an energy-loss estimate.\n\n")
    w("## Warnings\n\n")
    if summary["warnings"]:
        for warn in summary["warnings"]:
            w(f"- {warn}\n")
    else:
        w("- None.\n")
    rej = summary["diagnostics"]["selected_phase_rejections"]
    w("\n## Rejected candidates (selected phase)\n\n")
    for k, v in sorted(rej.items()):
        w(f"- {k}: {v}\n")
    w(f"\nExact rational re-checks of borderline distances: {summary['diagnostics']['exact_borderline_checks']}.\n\n")
    w("## Not provided by this module\n\nEnergy yield, shading losses, electrical strings, inverter selection, AC capacity, cable routing, structural checks, pile design, terrain fitting, cut/fill, code compliance and financial results.\n\n")
    w("## Provenance\n\n")
    for k in ("schema_version", "algorithm_version", "geometry_policy_version", "source_commit", "source_dirty", "created_at"):
        w(f"- {k}: `{provenance.get(k)}`\n")
    w("- dependencies: " + ", ".join(f"{k} {v}" for k, v in sorted(provenance.get("dependencies", {}).items())) + "\n")
