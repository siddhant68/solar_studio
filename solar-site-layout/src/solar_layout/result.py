"""Immutable result records in world coordinates, identities and the payload digest.

Identity layers (never mixed):
  input_digest   SHA-256 of the canonical normalized request without its `name`
  result_id      derived from input_digest + schema/algorithm/policy versions
  payload_digest SHA-256 over the canonical numerical payload (summary numbers, tables,
                 modules); excludes timestamps, provenance and transport wrappers
  artifact sha   SHA-256 of each exported file's bytes (exports module)
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterator

import numpy as np
import shapely

from . import ALGORITHM_VERSION, GEOMETRY_POLICY_VERSION, RESULT_SCHEMA, policy
from .jsonio import canonical_dumps, sha256_hex
from .layout import LayoutComputation


def result_id_for(input_digest: str) -> str:
    seed = "|".join([RESULT_SCHEMA, ALGORITHM_VERSION, GEOMETRY_POLICY_VERSION, input_digest])
    return "res_" + sha256_hex(seed)[:24]


def table_id(i: int, j: int) -> str:
    return f"T_j{j}_i{i}"


def module_id(i: int, j: int, r: int, c: int) -> str:
    return f"T_j{j}_i{i}_r{r}_c{c}"


def _world(arr: np.ndarray, origin: tuple[float, float]) -> np.ndarray:
    return arr + np.array(origin)


class ResultRecords:
    """World-coordinate records derived from one LayoutComputation."""

    def __init__(self, comp: LayoutComputation):
        self.comp = comp
        val = comp.validated
        self.val = val
        self.origin = val.origin
        self.result_id = result_id_for(val.input_digest)
        self.tables_world_corners = _world(comp.table_corners_local, self.origin)
        self.tables_world_origin = _world(comp.table_origin_local, self.origin)
        self.modules_world = _world(comp.module_corners_local, self.origin)
        self.summary = self._summary()
        self.payload_digest = self._payload_digest()
        self.summary["payload_digest"] = self.payload_digest

    # ---- summary ----------------------------------------------------------------------
    def _summary(self) -> dict[str, Any]:
        comp = self.comp
        val = self.val
        dims = val.dims
        n = val.normalized
        sel = comp.selected
        phases = [
            {
                "phase_index": [ph.p, ph.q],
                "offset_u_m": ph.offset_u_m,
                "offset_v_m": ph.offset_v_m,
                "table_count": ph.table_count,
                "module_count": ph.table_count * dims.modules_per_table,
                "candidates": ph.candidates,
            }
            for ph in comp.phases
        ]
        placement = {
            "mode": n["placement"]["mode"],
            "anchor_xy_m": n["placement"]["anchor_xy_m"],
            "lattice_period_u_m": comp.P,
            "row_pitch_m": comp.R,
            "table_gap_m": n["placement"]["table_gap_m"],
            "clear_row_gap_m": comp.R - dims.D,
            "minimum_clear_row_gap_m": n["placement"]["minimum_clear_row_gap_m"],
            "selected_phase_index": [sel.p, sel.q],
            "selected_offset_u_m": sel.offset_u_m,
            "selected_offset_v_m": sel.offset_v_m,
            "phase_candidates": phases,
        }
        if n["placement"]["mode"] == "phase_search_3x3":
            placement["search_scope"] = (
                "3x3 phase offsets (p/3, q/3) of the lattice period along u and v, p,q in {0,1,2}, "
                "with table type, tilt, azimuth and pitch unchanged"
            )
            placement["objective"] = "maximize placed module count"
            placement["tie_break"] = "lowest (p, q) in lexicographic order; phase (0,0) wins any tie it is part of"
            placement["optimality"] = "best_of_evaluated_candidates"
        else:
            placement["optimality"] = "fixed_lattice_no_search"
        return {
            "schema_version": RESULT_SCHEMA,
            "result_id": self.result_id,
            "input_digest": val.input_digest,
            "frame": n["frame"],
            "computation_frame": {
                "kind": "anchor_translated",
                "origin_world_xy_m": list(self.origin),
                "forward": "x_local = x_world - origin_x; y_local = y_world - origin_y",
                "inverse": "x_world = x_local + origin_x; y_world = y_local + origin_y",
                "rotation": "none",
            },
            "axes": {
                "facing_azimuth_deg": n["table"]["facing_azimuth_deg"],
                "u_table_width_axis": list(val.u),
                "v_uphill_axis": list(val.v),
                "convention": "u = (-cos A, sin A), v = (-sin A, -cos A); A clockwise from frame north",
            },
            "dimensions": {
                "module_orientation": n["module"]["orientation"],
                "module_w_across_m": dims.module_w,
                "module_l_upslope_m": dims.module_l,
                "rows": dims.rows,
                "columns": dims.columns,
                "module_gap_x_m": dims.gap_x,
                "module_gap_y_m": dims.gap_y,
                "table_width_W_m": dims.W,
                "table_slope_length_L_m": dims.L,
                "table_projected_depth_D_m": dims.D,
                "table_rise_H_m": dims.H,
                "tilt_deg": n["table"]["tilt_deg"],
                "lower_edge_height_m": dims.lower_edge_height,
                "upper_edge_height_m": dims.lower_edge_height + dims.H,
                "footprint_checked_W_m": comp.W_check,
                "footprint_checked_L_m": comp.L_check,
            },
            "placement": placement,
            "quantities": comp.quantities,
            "z_kind": "relative_flat_datum",
            "z_reference": "z = 0 is the layout's synthetic flat datum; heights are not surveyed elevations",
            "diagnostics": {k: v for k, v in comp.diagnostics.items() if k != "rejection_records"},
            "rejections": comp.diagnostics["rejection_records"],
            "warnings": comp.diagnostics["warnings"],
            "geometry_policy": policy.GEOMETRY_POLICY,
            "identity": {
                "result_id_derivation": "res_ + sha256(result schema | algorithm version | geometry policy version | input digest)[:24]",
                "algorithm_version": ALGORITHM_VERSION,
                "geometry_policy_version": GEOMETRY_POLICY_VERSION,
            },
        }

    # ---- records ----------------------------------------------------------------------
    def table_records(self) -> Iterator[dict[str, Any]]:
        dims = self.val.dims
        ij = self.comp.selected.accepted_ij
        for seq in range(ij.shape[0]):
            i, j = int(ij[seq, 0]), int(ij[seq, 1])
            yield {
                "seq": seq,
                "table_id": table_id(i, j),
                "i": i,
                "j": j,
                "origin_xy_m": self.tables_world_origin[seq].tolist(),
                "footprint_xy_m": self.tables_world_corners[seq].tolist(),
                "lower_edge_z_m": dims.lower_edge_height,
                "upper_edge_z_m": dims.lower_edge_height + dims.H,
                "module_count": dims.modules_per_table,
            }

    def module_records(self) -> Iterator[dict[str, Any]]:
        comp = self.comp
        ij = comp.selected.accepted_ij
        rc = comp.module_rc
        z = comp.module_z
        power = self.val.normalized["module"]["power_wp"]
        n_per = rc.shape[0]
        seq = 0
        for t in range(ij.shape[0]):
            i, j = int(ij[t, 0]), int(ij[t, 1])
            tid = table_id(i, j)
            corners_xy = self.modules_world[t]
            for m in range(n_per):
                r, c = int(rc[m, 0]), int(rc[m, 1])
                xy = corners_xy[m]
                yield {
                    "seq": seq,
                    "module_id": module_id(i, j, r, c),
                    "table_id": tid,
                    "table_i": i,
                    "table_j": j,
                    "row": r,
                    "column": c,
                    "corners_xyz_m": [[float(xy[k, 0]), float(xy[k, 1]), float(z[m, k])] for k in range(4)],
                    "power_wp": power,
                }
                seq += 1

    def numeric_summary(self) -> dict[str, Any]:
        s = self.summary
        return {
            "schema_version": s["schema_version"],
            "input_digest": s["input_digest"],
            "computation_frame": s["computation_frame"],
            "axes": s["axes"],
            "dimensions": s["dimensions"],
            "placement": s["placement"],
            "quantities": s["quantities"],
        }

    def _payload_digest(self) -> str:
        h = hashlib.sha256()
        h.update(canonical_dumps(self.numeric_summary()).encode())
        for rec in self.table_records():
            h.update(b"\n")
            h.update(canonical_dumps(rec).encode())
        for rec in self.module_records():
            h.update(b"\n")
            h.update(canonical_dumps(rec).encode())
        return h.hexdigest()

    def region_geojson(self) -> dict[str, Any]:
        from shapely.geometry import mapping

        def world(g):
            if g is None or g.is_empty:
                return None
            return mapping(shapely.transform(g, lambda c: c + np.array(self.origin)))

        return {
            "admissible_region": world(self.comp.admissible_local),
            "forbidden_region": world(self.comp.forbidden_local),
        }
