"""V04 (SVG/DXF/CSV/JSON match the immutable result) and V05 (calculation report)."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
import xml.etree.ElementTree as ET
import zipfile

import ezdxf
import numpy as np
import pytest

from conftest import load_fixture, shifted
from solar_layout.exports.csvx import CSV_COLUMNS
from solar_layout.service import SolarService

SVG_NS = {"s": "http://www.w3.org/2000/svg"}


def projected_rotated_request():
    req = load_fixture("obstacle.request.json")
    req = shifted(req, 446_000.0, 4_412_000.0)
    req["name"] = "Projected rotated regression"
    req["frame"] = {"kind": "projected_cartesian", "id": "utm33n", "crs": "EPSG:32633", "units": "m", "axes": {"x": "east", "y": "north"}}
    req["boundary"]["coordinates"].append([[446_009.0, 4_412_009.0], [446_010.0, 4_412_009.0], [446_010.0, 4_412_010.0], [446_009.0, 4_412_010.0], [446_009.0, 4_412_009.0]])
    req["table"]["facing_azimuth_deg"] = 197.0
    req["table"]["module_gap_x_m"] = 0.05
    req["placement"]["table_gap_m"] = 0.6
    req["exclusions"][0]["keepout_m"] = 0.5
    req["perimeter_setback_m"] = 0.5
    return req


CASES = {
    "obstacle": lambda: load_fixture("obstacle.request.json"),
    "multipolygon": lambda: load_fixture("multipolygon.request.json"),
    "projected_rotated": projected_rotated_request,
}


@pytest.fixture(scope="module", params=list(CASES))
def exported(request, tmp_path_factory):
    svc = SolarService(tmp_path_factory.mktemp(request.param) / "data")
    res = svc.generate_layout(request=CASES[request.param]())
    rid = res["result_id"]
    files = {fmt: svc.export_layout(rid, fmt) for fmt in ("json", "csv", "svg", "dxf", "report", "bundle")}
    tables = list(svc.store.iter_records(rid, "tables"))
    modules = list(svc.store.iter_records(rid, "modules"))
    return svc, res, files, tables, modules


def read(svc, meta) -> bytes:
    return (svc.store.export_root / meta["path"]).read_bytes()


def test_v04_files_hashes_recorded(exported):
    svc, res, files, _, _ = exported
    for fmt, meta in files.items():
        data = read(svc, meta)
        assert hashlib.sha256(data).hexdigest() == meta["sha256"] and len(data) == meta["bytes"]


def test_v04_csv_matches_every_module(exported):
    svc, res, files, tables, modules = exported
    rows = list(csv.reader(io.StringIO(read(svc, files["csv"]).decode())))
    assert rows[0] == CSV_COLUMNS
    body = rows[1:]
    assert len(body) == len(modules) == res["summary"]["quantities"]["module_count"]
    for row, m in zip(body, modules):
        assert row[0] == m["module_id"] and row[1] == m["table_id"]
        assert [int(row[2]), int(row[3]), int(row[4]), int(row[5])] == [m["table_i"], m["table_j"], m["row"], m["column"]]
        vals = [float(v) for v in row[6:18]]
        assert vals == [v for c in m["corners_xyz_m"] for v in c]  # exact round trip
    total_w = sum(float(r[18]) for r in body)
    assert total_w / 1000 == pytest.approx(res["summary"]["quantities"]["dc_capacity_kwp"], abs=1e-9)


def test_v04_json_matches_result(exported):
    svc, res, files, tables, modules = exported
    doc = json.loads(read(svc, files["json"]))
    assert doc["result"]["result_id"] == res["result_id"]
    assert doc["result"]["payload_digest"] == res["payload_digest"]
    assert doc["tables"] == tables and doc["modules"] == modules
    assert doc["request"]["frame"] == res["summary"]["frame"]
    assert doc["provenance"]["algorithm_version"] == res["provenance"]["algorithm_version"]


def test_v04_svg_vertices_map_back_to_result(exported):
    svc, res, files, tables, modules = exported
    root = ET.fromstring(read(svc, files["svg"]))
    assert root.get("width").endswith("mm") and root.get("viewBox").startswith("0 0 ")
    plan = root.find("s:svg[@id='plan']", SVG_NS)
    x0, y1 = float(plan.get("data-x0")), float(plan.get("data-y1"))
    scale = int(plan.get("data-scale"))
    vb = [float(v) for v in plan.get("viewBox").split()]
    # page millimetres vs plan metres: plan width (mm) == viewBox width (m) * 1000 / scale
    assert float(plan.get("width")) == pytest.approx(vb[2] * 1000 / scale, rel=1e-9)
    polys = {p.get("data-module-id"): p.get("points") for p in plan.iter("{http://www.w3.org/2000/svg}polygon") if p.get("data-module-id")}
    tpolys = {p.get("data-table-id"): p.get("points") for p in plan.iter("{http://www.w3.org/2000/svg}polygon") if p.get("data-table-id")}
    assert set(polys) == {m["module_id"] for m in modules}
    assert set(tpolys) == {t["table_id"] for t in tables}

    def back(points):
        out = []
        for pair in points.split():
            X, Y = (float(v) for v in pair.split(","))
            out.append((X + x0, y1 - Y))
        return np.array(out)

    for m in modules:
        assert np.abs(back(polys[m["module_id"]]) - np.array([c[:2] for c in m["corners_xyz_m"]])).max() <= 1e-9
    for t in tables:
        assert np.abs(back(tpolys[t["table_id"]]) - np.array(t["footprint_xy_m"])).max() <= 1e-9
    text = read(svc, files["svg"]).decode()
    for needle in ("north-arrow", "scale-bar", "Legend", "metres", res["result_id"]):
        assert needle in text


def test_v04_dxf_reopens_with_units_layers_counts_extents(exported):
    svc, res, files, tables, modules = exported
    doc = ezdxf.readfile(str(svc.store.export_root / files["dxf"]["path"]))
    assert doc.header["$INSUNITS"] == 6 and doc.header["$MEASUREMENT"] == 1
    msp = doc.modelspace()
    by_layer: dict[str, list] = {}
    for e in msp.query("LWPOLYLINE"):
        assert e.closed
        by_layer.setdefault(e.dxf.layer, []).append(e)
    assert len(by_layer.get("MODULES", [])) == len(modules)
    assert len(by_layer.get("TABLES", [])) == len(tables)
    req = svc.store.get_result_row(res["result_id"])["request"]
    polys = [req["boundary"]["coordinates"]] if req["boundary"]["type"] == "Polygon" else req["boundary"]["coordinates"]
    assert len(by_layer["SITE_BOUNDARY"]) == len(polys)
    assert len(by_layer.get("SITE_HOLES", [])) == sum(len(p) - 1 for p in polys)
    xs = [p[0] for poly in polys for p in poly[0]]
    ys = [p[1] for poly in polys for p in poly[0]]
    pts = np.array([v[:2] for e in by_layer["SITE_BOUNDARY"] for v in e.get_points("xy")])
    assert pts[:, 0].min() == min(xs) and pts[:, 0].max() == max(xs)
    assert pts[:, 1].min() == min(ys) and pts[:, 1].max() == max(ys)
    rec = {m["module_id"]: m for m in modules}
    for e in by_layer.get("MODULES", []):
        mid = e.get_xdata("SOLAR_STUDIO")[0].value
        got = np.array(list(e.get_points("xy")))
        exp = np.array([c[:2] for c in rec[mid]["corners_xyz_m"]])
        assert np.abs(got - exp).max() <= 1e-9
    assert {e.get_xdata("SOLAR_STUDIO")[0].value for e in by_layer.get("TABLES", [])} == {t["table_id"] for t in tables}


def test_v04_bundle_manifest(exported):
    svc, res, files, _, _ = exported
    z = zipfile.ZipFile(io.BytesIO(read(svc, files["bundle"])))
    manifest = json.loads(z.read("manifest.json"))
    assert manifest["result_id"] == res["result_id"] and manifest["payload_digest"] == res["payload_digest"]
    assert manifest["input_digest"] == res["input_digest"] and manifest["frame"] == res["summary"]["frame"]
    assert manifest["versions"]["algorithm_version"]
    for f in manifest["files"]:
        assert hashlib.sha256(z.read(f["name"])).hexdigest() == f["sha256"]
    assert len(manifest["files"]) == 5


def test_v04_exports_are_deterministic(exported):
    svc, res, files, _, _ = exported
    again = svc.export_layout(res["result_id"], "svg")
    assert again["sha256"] == files["svg"]["sha256"]


def test_v05_report_reproduces_arithmetic_and_states_assumptions(exported):
    svc, res, files, tables, modules = exported
    text = read(svc, files["report"]).decode()
    q = res["summary"]["quantities"]
    d = res["summary"]["dimensions"]
    req = svc.store.get_result_row(res["result_id"])["request"]
    t = req["table"]
    assert f"= {q['table_count']} × {t['rows']} × {t['columns']} = **{q['module_count']}**" in text
    assert f"{q['module_count']} × {req['module']['power_wp']!r} / 1000" in text
    assert "Table width W" in text and "Projected depth D" in text and "Total rise H" in text
    for key in ("Gross site area", "Buildable area", "Physical module area", "Projected module area", "Table footprint area"):
        assert key in text
    assert "projected module area / gross site area" in text and "projected module area / buildable area" in text
    assert "relative_flat_datum" in text and "not surveyed elevations" in text
    assert "not an all-year shading guarantee" in text
    assert re.search(r"\bkWh\b", text) is None
    assert "No AC capacity" in text
    assert str(round(d["table_width_W_m"], 3))[:4] in text


def test_v04_tampered_export_is_rebuilt_not_served(tmp_path):
    from starlette.testclient import TestClient

    from solar_layout.http_app import create_app

    with TestClient(create_app(str(tmp_path / "d"))) as http:
        rid = http.post("/api/layouts", json={"request": load_fixture("obstacle.request.json")}).json()["result_id"]
        first = http.get(f"/api/layouts/{rid}/exports/csv")
        svc = http.app.state.service
        path = svc.store.export_root / svc.store.get_export(rid, "csv")["path"]
        path.write_text("tampered\n")
        again = http.get(f"/api/layouts/{rid}/exports/csv")
        assert again.status_code == 200 and again.content == first.content
        assert again.headers["x-content-sha256"] == hashlib.sha256(again.content).hexdigest()


def test_v05_empty_layout_report_has_null_ratio(tmp_path):
    svc = SolarService(tmp_path / "d")
    req = load_fixture("rectangle.request.json")
    req["perimeter_setback_m"] = 7.0
    r = svc.generate_layout(request=req)
    text = (svc.store.export_root / svc.export_layout(r["result_id"], "report")["path"]).read_text()
    assert "null (denominator is zero)" in text and "empty" in text
