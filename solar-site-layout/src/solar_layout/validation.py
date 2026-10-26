"""Validation and normalization of `solar.layout.request/1`.

Order: strict structure (JSON Schema) -> frame semantics -> per-ring geometry checks ->
supported envelope -> module/pitch feasibility. Every rejection is a typed field error
with a JSON-pointer `field`. Invalid sites are never repaired.
"""

from __future__ import annotations

import copy
import json
import math
from dataclasses import dataclass, field
from functools import lru_cache
from importlib import resources
from typing import Any

import jsonschema
import shapely
from shapely.geometry import MultiPolygon, Polygon

from . import REQUEST_SCHEMA, policy
from .errors import (
    INVALID_GEOMETRY,
    INVALID_INPUT,
    INVALID_PITCH,
    RESOURCE_LIMIT,
    UNSUPPORTED_FRAME,
    UNSUPPORTED_INPUT,
    DomainError,
    FieldError,
)
from .geometry import TableDims, normalize_azimuth, table_axes, table_dims
from .jsonio import digest_of

SUPPORTED_FRAME_KINDS = ("local_cartesian", "projected_cartesian")
# Identifiers of geographic (degree) reference systems. A frame naming one of these is a
# degree frame whatever its other fields say.
GEOGRAPHIC_IDENTIFIERS = {
    "epsg:4326",
    "epsg:4258",
    "epsg:4269",
    "epsg:4979",
    "epsg:4167",
    "ogc:crs84",
    "crs84",
    "urn:ogc:def:crs:ogc:1.3:crs84",
    "urn:ogc:def:crs:epsg::4326",
    "wgs84",
    "wgs 84",
}


@lru_cache(maxsize=None)
def load_schema(name: str) -> dict[str, Any]:
    text = resources.files("solar_layout").joinpath("schemas", name).read_text()
    return json.loads(text)


@lru_cache(maxsize=None)
def _validator(name: str) -> jsonschema.Draft202012Validator:
    schema = load_schema(name)
    jsonschema.Draft202012Validator.check_schema(schema)
    return jsonschema.Draft202012Validator(schema)


def pointer(path: Any) -> str:
    parts = [str(p).replace("~", "~0").replace("/", "~1") for p in path]
    return "/" + "/".join(parts) if parts else ""


def non_finite_errors(value: Any, path: tuple = ()) -> list[FieldError]:
    out: list[FieldError] = []
    if isinstance(value, float):
        if not math.isfinite(value):
            out.append(
                FieldError(INVALID_INPUT, pointer(path), "Non-finite number is not accepted", {"reason": "non_finite_number"})
            )
    elif isinstance(value, dict):
        for k, v in value.items():
            out.extend(non_finite_errors(v, path + (k,)))
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            out.extend(non_finite_errors(v, path + (i,)))
    return out


def schema_errors(raw: Any, schema_name: str) -> list[FieldError]:
    errors = []
    for err in _validator(schema_name).iter_errors(raw):
        errors.append(
            FieldError(
                INVALID_INPUT,
                pointer(err.absolute_path),
                err.message if len(err.message) < 300 else err.message[:297] + "...",
                {"reason": f"schema:{err.validator}"},
            )
        )
    errors.sort(key=lambda e: e.field)
    return errors


@dataclass
class Validated:
    normalized: dict[str, Any]
    input_digest: str
    origin: tuple[float, float]  # world anchor: computation-frame origin
    site_world: Polygon | MultiPolygon
    site_local: Polygon | MultiPolygon
    exclusions_local: list[tuple[str, Polygon | MultiPolygon, float]]
    dims: TableDims
    u: tuple[float, float]
    v: tuple[float, float]
    warnings: list[str] = field(default_factory=list)


def _geometry_from(geom: dict[str, Any], base: str, errors: list[FieldError]) -> Polygon | MultiPolygon | None:
    gtype = geom["type"]
    polys_coords = [geom["coordinates"]] if gtype == "Polygon" else geom["coordinates"]
    built: list[Polygon] = []
    ok = True
    for p_index, rings in enumerate(polys_coords):
        p_base = f"{base}/coordinates" if gtype == "Polygon" else f"{base}/coordinates/{p_index}"
        ring_ok = True
        for r_index, ring in enumerate(rings):
            r_path = f"{p_base}/{r_index}"
            for k, pos in enumerate(ring):
                if len(pos) != 2:
                    errors.append(
                        FieldError(
                            UNSUPPORTED_INPUT,
                            f"{r_path}/{k}",
                            "Z-bearing site coordinates are not supported; supply [x, y] in metres",
                            {"reason": "z_coordinate_unsupported"},
                        )
                    )
                    ring_ok = False
                    break
            if not ring_ok:
                continue
            if len(ring) < 4:
                errors.append(
                    FieldError(INVALID_GEOMETRY, r_path, "A ring needs at least 4 positions (closed, 3 distinct vertices)", {"reason": "too_few_positions"})
                )
                ring_ok = False
                continue
            if ring[0][0] != ring[-1][0] or ring[0][1] != ring[-1][1]:
                errors.append(
                    FieldError(INVALID_GEOMETRY, r_path, "Ring is not closed: the first and last positions must be identical", {"reason": "ring_not_closed"})
                )
                ring_ok = False
                continue
        if not ring_ok:
            ok = False
            continue
        shell = [(float(x), float(y)) for x, y in rings[0]]
        holes = [[(float(x), float(y)) for x, y in r] for r in rings[1:]]
        poly = Polygon(shell, holes)
        reason = shapely.is_valid_reason(poly)
        if reason != "Valid Geometry":
            errors.append(FieldError(INVALID_GEOMETRY, p_base, f"Invalid polygon: {reason}", {"reason": "geos_invalid", "geos": reason}))
            ok = False
            continue
        if not (poly.area > 0.0):
            errors.append(FieldError(INVALID_GEOMETRY, p_base, "Degenerate polygon with zero area", {"reason": "degenerate"}))
            ok = False
            continue
        for r_index, ring in enumerate(rings):
            ring_poly = Polygon([(float(x), float(y)) for x, y in ring])
            if not (abs(ring_poly.area) > 0.0):
                errors.append(FieldError(INVALID_GEOMETRY, f"{p_base}/{r_index}", "Degenerate ring with zero area", {"reason": "degenerate"}))
                ok = False
        built.append(poly)
    if not ok:
        return None
    if gtype == "Polygon":
        return built[0]
    multi = MultiPolygon(built)
    reason = shapely.is_valid_reason(multi)
    if reason != "Valid Geometry":
        errors.append(FieldError(INVALID_GEOMETRY, f"{base}/coordinates", f"Invalid MultiPolygon: {reason}", {"reason": "geos_invalid", "geos": reason}))
        return None
    return multi


def _iter_positions(geom: dict[str, Any], base: str):
    polys = [geom["coordinates"]] if geom["type"] == "Polygon" else geom["coordinates"]
    for p_index, rings in enumerate(polys):
        p_base = f"{base}/coordinates" if geom["type"] == "Polygon" else f"{base}/coordinates/{p_index}"
        for r_index, ring in enumerate(rings):
            for k, pos in enumerate(ring):
                yield f"{p_base}/{r_index}/{k}", pos


def _frame_errors(frame: dict[str, Any]) -> list[FieldError]:
    errors: list[FieldError] = []
    kind = frame["kind"]
    if kind not in SUPPORTED_FRAME_KINDS:
        errors.append(
            FieldError(
                UNSUPPORTED_FRAME,
                "/frame/kind",
                f"Frame kind {kind!r} is not supported; use local_cartesian or projected_cartesian (metric, x East, y North)",
                {"supported": list(SUPPORTED_FRAME_KINDS)},
            )
        )
    if frame["units"] != "m":
        errors.append(
            FieldError(
                UNSUPPORTED_FRAME,
                "/frame/units",
                f"Units {frame['units']!r} are not supported; coordinates must be metres (\"m\"). Geographic degrees are not accepted",
                {"supported": ["m"]},
            )
        )
    axes = frame["axes"]
    if axes.get("x") != "east" or axes.get("y") != "north":
        errors.append(
            FieldError(UNSUPPORTED_FRAME, "/frame/axes", "Axes must be x=east, y=north", {"supported": {"x": "east", "y": "north"}})
        )
    for key in ("id", "crs"):
        ident = frame.get(key)
        if isinstance(ident, str) and ident.strip().lower() in GEOGRAPHIC_IDENTIFIERS:
            errors.append(
                FieldError(
                    UNSUPPORTED_FRAME,
                    f"/frame/{key}",
                    f"{ident!r} names a geographic (degree) reference system; supply projected or local metric coordinates",
                    {"reason": "geographic_crs"},
                )
            )
    if kind == "projected_cartesian" and not frame.get("crs"):
        errors.append(FieldError(INVALID_INPUT, "/frame/crs", "projected_cartesian frames must name their CRS identifier in frame.crs", {"reason": "missing_crs"}))
    return errors


def normalize(raw: dict[str, Any]) -> dict[str, Any]:
    n = copy.deepcopy(raw)

    def fl(x: Any) -> float:
        return float(x) + 0.0

    def geom(g: dict[str, Any]) -> dict[str, Any]:
        if g["type"] == "Polygon":
            return {"type": "Polygon", "coordinates": [[[fl(x), fl(y)] for x, y in ring] for ring in g["coordinates"]]}
        return {
            "type": "MultiPolygon",
            "coordinates": [[[[fl(x), fl(y)] for x, y in ring] for ring in poly] for poly in g["coordinates"]],
        }

    n["boundary"] = geom(n["boundary"])
    n["perimeter_setback_m"] = fl(n["perimeter_setback_m"])
    n["exclusions"] = [
        {"id": e["id"], "geometry": geom(e["geometry"]), "keepout_m": fl(e["keepout_m"])} for e in n["exclusions"]
    ]
    m = n["module"]
    for k in ("width_m", "length_m", "power_wp"):
        m[k] = fl(m[k])
    t = n["table"]
    t["rows"] = int(t["rows"])
    t["columns"] = int(t["columns"])
    for k in ("module_gap_x_m", "module_gap_y_m", "tilt_deg", "lower_edge_height_m"):
        t[k] = fl(t[k])
    t["facing_azimuth_deg"] = normalize_azimuth(t["facing_azimuth_deg"])
    p = n["placement"]
    p["anchor_xy_m"] = [fl(p["anchor_xy_m"][0]), fl(p["anchor_xy_m"][1])]
    for k in ("table_gap_m", "row_pitch_m", "minimum_clear_row_gap_m"):
        p[k] = fl(p[k])
    return n


def numerical_identity_view(normalized: dict[str, Any]) -> dict[str, Any]:
    """The part of a normalized request that determines the numerical result.

    `name` is a label; it is excluded so renaming never changes result identity.
    """
    view = {k: v for k, v in normalized.items() if k != "name"}
    return view


def validate_layout_request(raw: Any) -> Validated:
    if not isinstance(raw, dict):
        raise DomainError(INVALID_INPUT, "Request must be a JSON object", field="")
    errors = non_finite_errors(raw)
    if errors:
        raise DomainError.from_field_errors(errors)
    errors = schema_errors(raw, "solar.layout.request.v1.schema.json")
    if errors:
        raise DomainError.from_field_errors(errors)

    errors = _frame_errors(raw["frame"])

    # Envelope checks on raw coordinates before any geometry work.
    limit_errors: list[FieldError] = []
    count = 0
    for path, pos in _iter_positions(raw["boundary"], "/boundary"):
        count += 1
        for value in pos[:2]:
            if abs(value) > policy.MAX_ABS_COORDINATE_M:
                limit_errors.append(
                    FieldError(RESOURCE_LIMIT, path, f"Coordinate magnitude exceeds the supported {policy.MAX_ABS_COORDINATE_M:.0f} m", {"limit": "max_abs_coordinate_m", "value": value})
                )
                break
        if len(limit_errors) > 20:
            break
    if count > policy.MAX_BOUNDARY_VERTICES:
        limit_errors.append(FieldError(RESOURCE_LIMIT, "/boundary", f"Boundary has {count} vertices; the supported maximum is {policy.MAX_BOUNDARY_VERTICES}", {"limit": "max_boundary_vertices"}))
    ex_count = 0
    for i, ex in enumerate(raw["exclusions"]):
        for path, pos in _iter_positions(ex["geometry"], f"/exclusions/{i}/geometry"):
            ex_count += 1
            if any(abs(v) > policy.MAX_ABS_COORDINATE_M for v in pos[:2]):
                limit_errors.append(FieldError(RESOURCE_LIMIT, path, "Coordinate magnitude exceeds the supported envelope", {"limit": "max_abs_coordinate_m"}))
                break
    if ex_count > policy.MAX_EXCLUSION_VERTICES_TOTAL:
        limit_errors.append(FieldError(RESOURCE_LIMIT, "/exclusions", "Exclusions exceed the supported total vertex count", {"limit": "max_exclusion_vertices_total"}))
    anchor = raw["placement"]["anchor_xy_m"]
    if any(abs(v) > policy.MAX_ABS_COORDINATE_M for v in anchor):
        limit_errors.append(FieldError(RESOURCE_LIMIT, "/placement/anchor_xy_m", "Anchor coordinate magnitude exceeds the supported envelope", {"limit": "max_abs_coordinate_m"}))
    for key in ("width_m", "length_m"):
        value = raw["module"][key]
        if value < policy.MIN_MODULE_DIMENSION_M:
            limit_errors.append(FieldError(RESOURCE_LIMIT, f"/module/{key}", f"Module dimension {value} m is below the supported minimum {policy.MIN_MODULE_DIMENSION_M} m", {"limit": "min_module_dimension_m"}))
        elif value > policy.MAX_MODULE_DIMENSION_M:
            limit_errors.append(FieldError(RESOURCE_LIMIT, f"/module/{key}", f"Module dimension {value} m is above the supported maximum {policy.MAX_MODULE_DIMENSION_M} m", {"limit": "max_module_dimension_m"}))
    errors.extend(limit_errors)
    if errors:
        raise DomainError.from_field_errors(errors)

    geo_errors: list[FieldError] = []
    site_world = _geometry_from(raw["boundary"], "/boundary", geo_errors)
    exclusions_world = []
    ids: set[str] = set()
    for i, ex in enumerate(raw["exclusions"]):
        if ex["id"] in ids:
            geo_errors.append(FieldError(INVALID_INPUT, f"/exclusions/{i}/id", f"Duplicate exclusion id {ex['id']!r}", {"reason": "duplicate_id"}))
        ids.add(ex["id"])
        g = _geometry_from(ex["geometry"], f"/exclusions/{i}/geometry", geo_errors)
        exclusions_world.append(g)
    if geo_errors:
        raise DomainError.from_field_errors(geo_errors)
    assert site_world is not None

    minx, miny, maxx, maxy = site_world.bounds
    diagonal = math.hypot(maxx - minx, maxy - miny)
    if diagonal > policy.MAX_SITE_DIAGONAL_M:
        raise DomainError(
            RESOURCE_LIMIT,
            f"Site bounding-box diagonal {diagonal:.1f} m exceeds the supported {policy.MAX_SITE_DIAGONAL_M:.0f} m",
            field="/boundary",
            details={"limit": "max_site_diagonal_m", "value": diagonal},
        )
    ax, ay = float(anchor[0]), float(anchor[1])
    dx = max(minx - ax, 0.0, ax - maxx)
    dy = max(miny - ay, 0.0, ay - maxy)
    if math.hypot(dx, dy) > policy.MAX_ANCHOR_DISTANCE_FROM_SITE_BBOX_M:
        raise DomainError(
            RESOURCE_LIMIT,
            "Placement anchor is too far from the site; it must lie within "
            f"{policy.MAX_ANCHOR_DISTANCE_FROM_SITE_BBOX_M:.0f} m of the site bounding box",
            field="/placement/anchor_xy_m",
            details={"limit": "max_anchor_distance_from_site_bbox_m"},
        )

    module = raw["module"]
    if module["width_m"] > module["length_m"]:
        raise DomainError(
            INVALID_INPUT,
            "module.width_m is the short side and must not exceed module.length_m; use orientation to rotate the module",
            field="/module/width_m",
            details={"reason": "width_exceeds_length"},
        )

    normalized = normalize(raw)
    dims = table_dims(normalized["module"], normalized["table"])
    placement = normalized["placement"]
    R = placement["row_pitch_m"]
    gap = placement["minimum_clear_row_gap_m"]
    if R < dims.D:
        raise DomainError(
            INVALID_PITCH,
            f"Row pitch {R} m is less than the projected table depth D = {dims.D} m: consecutive rows would physically overlap",
            field="/placement/row_pitch_m",
            details={"row_pitch_m": R, "projected_depth_m": dims.D, "minimum_clear_row_gap_m": gap, "required_pitch_m": dims.D + gap},
        )
    if R < dims.D + gap - policy.PITCH_TOLERANCE_M:
        raise DomainError(
            INVALID_PITCH,
            f"Row pitch {R} m is below D + minimum clear gap = {dims.D + gap} m (lower edge to lower edge); the pitch is not changed automatically",
            field="/placement/row_pitch_m",
            details={"row_pitch_m": R, "projected_depth_m": dims.D, "minimum_clear_row_gap_m": gap, "required_pitch_m": dims.D + gap, "tolerance_m": policy.PITCH_TOLERANCE_M},
        )

    origin = (normalized["placement"]["anchor_xy_m"][0], normalized["placement"]["anchor_xy_m"][1])

    def to_local(g):
        return shapely.transform(g, lambda c: c - origin)

    site_world_n = _geometry_from(normalized["boundary"], "/boundary", [])
    site_local = to_local(site_world_n)
    exclusions_local = []
    warnings: list[str] = []
    for ex, g in zip(normalized["exclusions"], exclusions_world):
        assert g is not None
        local = to_local(g)
        exclusions_local.append((ex["id"], local, ex["keepout_m"]))
        if shapely.distance(local, site_local) > ex["keepout_m"]:
            warnings.append(f"Exclusion {ex['id']} and its keepout lie entirely outside the site; it has no effect")
    u, v = table_axes(normalized["table"]["facing_azimuth_deg"])
    return Validated(
        normalized=normalized,
        input_digest=digest_of(numerical_identity_view(normalized)),
        origin=origin,
        site_world=site_world_n,
        site_local=site_local,
        exclusions_local=exclusions_local,
        dims=dims,
        u=u,
        v=v,
        warnings=warnings,
    )


assert REQUEST_SCHEMA == "solar.layout.request/1"
