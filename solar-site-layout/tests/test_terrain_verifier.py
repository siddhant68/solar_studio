"""Independent verifier: TV01 (independence) and TV02 (fixture T10 corruptions).

The verifier is given the stored records with one planted corruption each and must reject
them, naming the failing checks listed in fixtures/cases/T10.json.
"""

from __future__ import annotations

import ast
import copy
import sqlite3

import pytest

from solar_layout.errors import DomainError
from solar_terrain.source import check_source, load_source
from solar_terrain.verify import verify_placement
from terrain_helpers import ROOT, all_items, case, place_case, prepare, services

PKG = ROOT / "src" / "solar_terrain"


class Placed:
    def __init__(self, ts, svc, pid):
        row = ts.store.get_placement_row(pid)
        self.terrain = ts.store.get_terrain_row(row["terrain_id"])
        self.src = load_source(svc, check_source(svc, row["source_result_id"], row["source_payload_digest"]))
        arr = ts.store.load_arrays(row["terrain_id"])
        self.V, self.T = arr["vertices"], arr["triangles"]
        self.request = row["request"]
        self.summary = row["summary"]
        self.tables = all_items(ts, pid, "tables")
        self.modules = all_items(ts, pid, "modules")
        self.supports = all_items(ts, pid, "supports")

    def verify(self, summary=None, tables=None, modules=None, supports=None):
        return verify_placement(
            self.src,
            self.terrain,
            self.V,
            self.T,
            self.request,
            summary if summary is not None else self.summary,
            tables if tables is not None else self.tables,
            modules if modules is not None else self.modules,
            supports if supports is not None else self.supports,
        )


@pytest.fixture
def svcs(tmp_path):
    return services(tmp_path / "data")


def placed(svcs, case_id: str) -> Placed:
    svc, ts = svcs
    _, out = place_case(ts, svc, case_id)
    return Placed(ts, svc, out["placement_id"])


def failed(result) -> set[str]:
    return {k for k, v in result["checks"].items() if not v["ok"]}


def m_lowered(p):
    t = copy.deepcopy(p.tables)
    t[0]["lower_edge_z_m"] -= 0.3
    m = copy.deepcopy(p.modules)
    for rec in m:
        if rec["table_id"] == t[0]["table_id"]:
            for c in rec["corners_xyz_m"]:
                c[2] -= 0.3
    return p.verify(tables=t, modules=m)


def m_corner(p):
    m = copy.deepcopy(p.modules)
    m[0]["corners_xyz_m"][2][2] += 0.01
    return p.verify(modules=m)


def m_min_clearance(p):
    t = copy.deepcopy(p.tables)
    t[0]["min_clearance_m"] = 0.8
    return p.verify(tables=t)


def m_unknown_as_placed(p):
    t = copy.deepcopy(p.tables)
    rec = t[0]
    assert rec["status"] == "unknown_ground"
    rec.update(status="placed", reasons=[], uncovered_area_m2=0.0, covered_area_m2=8.0, lower_edge_z_m=10.5, upper_edge_z_m=10.5, vertical_lift_m=9.7, min_clearance_m=0.5, min_clearance_at_xy_m=[2.0, 3.0], max_clearance_m=0.5, max_ground_slope_deg=0.0, mean_ground_gradient_uv=[0.0, 0.0])
    return p.verify(tables=t)


def m_support(p):
    s = copy.deepcopy(p.supports)
    s[0]["above_ground_m"] += 0.1
    return p.verify(supports=s)


def m_source_digest(p):
    s = copy.deepcopy(p.summary)
    s["source_layout"]["payload_digest"] = "f" * 64
    return p.verify(summary=s)


def m_footprint(p):
    t = copy.deepcopy(p.tables)
    t[1]["footprint_xy_m"] = [[x + 0.1, y] for x, y in t[1]["footprint_xy_m"]]
    return p.verify(tables=t)


def m_capacity(p):
    s = copy.deepcopy(p.summary)
    s["counts"]["placed_dc_capacity_kwp"] += 0.55
    return p.verify(summary=s)


def m_datum(p):
    s = copy.deepcopy(p.summary)
    s["vertical"]["crs"] = "EPSG:5703"
    return p.verify(summary=s)


def m_over_lifted(p):
    t = copy.deepcopy(p.tables)
    tid = t[0]["table_id"]
    for k in ("lower_edge_z_m", "upper_edge_z_m", "vertical_lift_m", "min_clearance_m", "max_clearance_m"):
        t[0][k] += 1.0
    m = copy.deepcopy(p.modules)
    for rec in m:
        if rec["table_id"] == tid:
            for c in rec["corners_xyz_m"]:
                c[2] += 1.0
    s = copy.deepcopy(p.supports)
    for rec in s:
        if rec["table_id"] == tid:
            rec["top_z_m"] += 1.0
            rec["above_ground_m"] += 1.0
    return p.verify(tables=t, modules=m, supports=s)


# (T10 change text, base case, mutation)
MUTATIONS = [
    ("tables[0].lower_edge_z_m -= 0.3 and every module z of that table -= 0.3", "T03", m_lowered),
    ("one module corner z += 0.01", "T03", m_corner),
    ("tables[0].min_clearance_m reported as 0.8 (corner value)", "T03", m_min_clearance),
    ("T04 table reported as placed at 10.5", "T04", m_unknown_as_placed),
    ("a support above_ground_m changed by +0.1", "T03", m_support),
    ("source payload_digest in the summary replaced", "T03", m_source_digest),
    ("a T01 table record's footprint shifted by 0.1 m in x", "T01", m_footprint),
    ("placed_dc_kwp changed while records unchanged", "T01", m_capacity),
    ("vertical.crs in the summary changed", "T03", m_datum),
    ("table lifted 1 m higher than the minimum (clearance still satisfied)", "T03", m_over_lifted),
]


def test_t10_lists_exactly_these_mutations():
    assert [m["change"] for m in case("T10")["mutations"]] == [m[0] for m in MUTATIONS]


@pytest.mark.parametrize("index", range(len(MUTATIONS)), ids=[m[0][:40] for m in MUTATIONS])
def test_tv02_corruptions_are_rejected(svcs, index):
    change, base, mutate = MUTATIONS[index]
    spec = case("T10")["mutations"][index]
    p = placed(svcs, base)
    assert p.verify()["ok"], "the unmodified placement must pass"
    res = mutate(p)
    assert res["ok"] is False
    bad = failed(res)
    assert set(spec["must_fail"]) <= bad, (change, sorted(bad))
    if index == 9:
        assert "clearance" not in bad  # still clears the ground; only the policy is violated


def test_verification_failure_stores_nothing(svcs, monkeypatch):
    svc, ts = svcs
    req = prepare(ts, svc, case("T03"))
    import solar_terrain.service as service

    real = service.place

    def lowered(*a, **k):
        pl = real(*a, **k)
        pl.tables[0]["lower_edge_z_m"] -= 0.3
        return pl

    monkeypatch.setattr(service, "place", lowered)
    with pytest.raises(DomainError) as ei:
        ts.place_on_terrain(req)
    assert ei.value.code == "VERIFICATION_FAILED"
    assert "clearance" in ei.value.details["failed_checks"]
    with sqlite3.connect(ts.store.db_path) as con:
        assert con.execute("SELECT COUNT(*) FROM placements").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM placement_tables").fetchone()[0] == 0


def _imports(path):
    tree = ast.parse(path.read_text())
    out = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            out |= {a.name for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mod = n.module or ""
            if not n.level:
                out.add(mod)
            elif mod:
                out.add(f"solar_terrain.{mod}")
            else:
                # `from . import X`: X is a submodule if a file of that name exists, else a package attribute
                out |= {f"solar_terrain.{a.name}" if (PKG / f"{a.name}.py").exists() else "solar_terrain" for a in n.names}
    return out


def test_import_boundary():
    """CONTRACTS.md section 1 and PLAN.md section 7: the terrain package's only Module 01
    imports are solar_layout.errors and solar_layout.jsonio; the verifier shares no
    geometry code with the engine."""
    for path in PKG.glob("*.py"):
        mods = _imports(path)
        m01 = {m for m in mods if m.split(".")[0] == "solar_layout"}
        assert m01 <= {"solar_layout.errors", "solar_layout.jsonio"}, (path.name, m01)
    verify_imports = _imports(PKG / "verify.py")
    forbidden = {"solar_terrain.engine", "solar_terrain.predicates", "solar_terrain.surface", "solar_terrain.request", "solar_terrain.source", "solar_terrain.service", "shapely"}
    assert not verify_imports & forbidden, verify_imports & forbidden
    assert verify_imports <= {"__future__", "hashlib", "math", "re", "fractions", "typing", "numpy", "solar_layout.jsonio", "solar_terrain.policy", "solar_terrain.schemas", "solar_terrain"}, verify_imports
    for name in ("engine.py", "predicates.py", "surface.py"):
        assert "solar_terrain.verify" not in _imports(PKG / name), name


def test_verifier_does_not_call_the_engine(svcs, monkeypatch):
    """verify_stored_placement must succeed with every engine and predicate entry point
    disabled."""
    svc, ts = svcs
    _, out = place_case(ts, svc, "T05")
    import solar_terrain.engine as engine
    import solar_terrain.predicates as predicates

    def boom(*a, **k):
        raise AssertionError("the verifier called engine code")

    for mod in (engine, predicates):
        for name in dir(mod):
            obj = getattr(mod, name)
            if callable(obj) and getattr(obj, "__module__", None) == mod.__name__:
                monkeypatch.setattr(mod, name, boom)
    res = ts.verify_stored_placement(out["placement_id"])
    assert res["ok"], {k: v["failures"] for k, v in res["checks"].items() if not v["ok"]}
