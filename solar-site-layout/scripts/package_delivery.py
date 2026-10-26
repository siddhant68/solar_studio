"""Package and verify the delivery (D05) and reproduce from a fresh checkout (D01).

    .venv/bin/python scripts/package_delivery.py OUT_DIR [--no-repro] [--evidence-dir DIR]

* Git bundle of every branch (`git bundle create --all`), verified with `git bundle verify`
  and by cloning it and comparing the checked-out tree with HEAD.
* Source ZIP from `git archive HEAD` (tracked files only), verified with a CRC test, a
  file-list comparison against `git ls-tree`, and a scan for caches, virtual environments,
  databases, keys and the reference checkouts.
* SHA256SUMS.txt over the delivered files.
* Fresh checkout: clone from the bundle into an empty directory, `uv sync --frozen` with an
  empty uv cache (packages fetched from the index per uv.lock), the analytic CLI workflow,
  and the full pytest suite.
Writes evidence/delivery/{package-verification.json, reproduction.json, reproduction-log.txt},
or into --evidence-dir (used to verify archives of the final commit without changing it).
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
DELIV = ROOT / "evidence" / "delivery"
FORBIDDEN_PARTS = (".venv/", "__pycache__/", "node_modules/", ".pytest_cache/", "/data/", ".sqlite3", ".pem", "id_rsa", ".env", "references/agv", "pw-browsers")


def run(cmd, cwd=None, env=None, timeout=3600) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        while chunk := f.read(1 << 20):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    global DELIV
    out = Path(sys.argv[1]).resolve()
    repro = "--no-repro" not in sys.argv
    if "--evidence-dir" in sys.argv:
        DELIV = Path(sys.argv[sys.argv.index("--evidence-dir") + 1]).resolve()
    out.mkdir(parents=True, exist_ok=True)
    DELIV.mkdir(parents=True, exist_ok=True)
    status = run(["git", "-C", str(REPO), "status", "--porcelain"]).stdout.strip()
    head = run(["git", "-C", str(REPO), "rev-parse", "HEAD"]).stdout.strip()
    short = head[:10]
    branch = run(["git", "-C", str(REPO), "rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    bundle = out / f"solar_studio-{short}.bundle"
    zip_path = out / f"solar_studio-{short}-source.zip"
    for p in (bundle, zip_path):
        if p.exists():
            p.unlink()
    cmds = [
        f"git bundle create {bundle.name} --all",
        "git bundle verify " + bundle.name,
        f"git archive --format=zip --prefix=solar_studio/ -o {zip_path.name} HEAD",
    ]
    checks = {}
    b = run(["git", "-C", str(REPO), "bundle", "create", str(bundle), "--all"])
    checks["bundle_created"] = b.returncode == 0
    v = run(["git", "-C", str(REPO), "bundle", "verify", str(bundle)])
    checks["bundle_verify"] = v.returncode == 0
    a = run(["git", "-C", str(REPO), "archive", "--format=zip", "--prefix=solar_studio/", "-o", str(zip_path), "HEAD"])
    checks["zip_created"] = a.returncode == 0
    with zipfile.ZipFile(zip_path) as z:
        checks["zip_crc_ok"] = z.testzip() is None
        names = [n[len("solar_studio/"):] for n in z.namelist() if not n.endswith("/")]
    tracked = run(["git", "-C", str(REPO), "ls-tree", "-r", "--name-only", "HEAD"]).stdout.split()
    checks["zip_matches_tracked_files"] = sorted(names) == sorted(tracked)
    bad = [n for n in names if any(f in "/" + n for f in FORBIDDEN_PARTS)]
    checks["no_caches_venvs_db_keys_or_reference_checkouts"] = not bad
    with zipfile.ZipFile(zip_path) as z:
        sizes = sorted(((z.getinfo("solar_studio/" + n).file_size, n) for n in names), reverse=True)
    tmp = Path(tempfile.mkdtemp(prefix="solar-verify-"))
    try:
        clone = tmp / "from-bundle"
        c = run(["git", "clone", "-q", "--branch", branch, str(bundle), str(clone)])
        checks["bundle_clone"] = c.returncode == 0
        checks["bundle_clone_head_matches"] = run(["git", "-C", str(clone), "rev-parse", "HEAD"]).stdout.strip() == head
        checks["bundle_clone_tree_matches"] = run(["git", "-C", str(clone), "rev-parse", "HEAD^{tree}"]).stdout.strip() == run(["git", "-C", str(REPO), "rev-parse", "HEAD^{tree}"]).stdout.strip()
        files = [bundle, zip_path]
        sums = "".join(f"{sha(f)}  {f.name}\n" for f in files)
        (out / "SHA256SUMS.txt").write_text(sums)
        pkg = {
            "passed": all(checks.values()) and not status,
            "working_tree_clean_at_packaging": not status,
            "head": head,
            "branch": branch,
            "commands": cmds,
            "checks": checks,
            "files": [{"name": f.name, "bytes": f.stat().st_size, "sha256": sha(f)} for f in files],
            "zip_file_count": len(names),
            "largest_files_in_zip": [{"path": n, "bytes": s} for s, n in sizes[:8]],
            "forbidden_hits": bad,
            "summary": f"bundle {bundle.name} and source zip {zip_path.name} built from {head}; " + ", ".join(f"{k}={v}" for k, v in checks.items()),
        }
        (DELIV / "package-verification.json").write_text(json.dumps(pkg, indent=1))
        print(json.dumps(checks))
        if not repro:
            return 0 if pkg["passed"] else 1
        # ---- D01 fresh checkout reproduction ------------------------------------------------
        log = []
        env = dict(os.environ)
        env["UV_CACHE_DIR"] = str(tmp / "uv-cache")  # empty cache: install strictly from the lock
        env.pop("VIRTUAL_ENV", None)
        app = clone / "solar-site-layout"
        steps = [
            ("uv sync --frozen", ["uv", "sync", "--frozen", "--python", "3.12"], app),
            ("generate rectangle", [str(app / ".venv/bin/solar-layout"), "--data-dir", str(tmp / "repro-data"), "generate", str(clone / "handoffs/module-01/fixtures/rectangle.request.json")], app),
            ("generate obstacle", [str(app / ".venv/bin/solar-layout"), "--data-dir", str(tmp / "repro-data"), "generate", str(clone / "handoffs/module-01/fixtures/obstacle.request.json")], app),
            ("pitch 3-4-5", [str(app / ".venv/bin/solar-layout"), "--data-dir", str(tmp / "repro-data"), "pitch", str(clone / "handoffs/module-01/fixtures/pitch-3-4-5.request.json")], app),
            ("pytest", [str(app / ".venv/bin/python"), "-m", "pytest", "-q", "-p", "no:cacheprovider"], app),
        ]
        results = {}
        ok = True
        for name, cmd, cwd in steps:
            t0 = time.time()
            p = run(cmd, cwd=str(cwd), env=env, timeout=3600)
            dt = time.time() - t0
            log.append(f"$ {' '.join(str(c).replace(str(tmp), '<tmp>') for c in cmd)}\n# exit {p.returncode} in {dt:.1f}s\n{p.stdout[-3000:]}\n{p.stderr[-2000:]}\n")
            results[name] = {"exit": p.returncode, "seconds": round(dt, 1)}
            if name.startswith("generate") or name.startswith("pitch"):
                try:
                    res = json.loads(p.stdout)["result"]
                    results[name]["result"] = res.get("summary", {}).get("quantities", {}).get("module_count") if "summary" in res else res.get("recommended_pitch_m")
                except (ValueError, KeyError, TypeError):
                    results[name]["result"] = None
            if name == "pytest":
                results[name]["tail"] = (p.stdout.strip().splitlines() or [""])[-1]
            ok = ok and p.returncode == 0
        expect = results.get("generate rectangle", {}).get("result") == 24 and results.get("generate obstacle", {}).get("result") == 20 and abs((results.get("pitch 3-4-5", {}).get("result") or 0) - 7.0) < 1e-9
        rep = {
            "passed": ok and expect,
            "head": head,
            "source": f"git clone of {bundle.name} (branch {branch}) into an empty temporary directory",
            "uv_cache": "empty temporary UV_CACHE_DIR (all packages fetched per uv.lock)",
            "uv_version": run(["uv", "--version"]).stdout.strip(),
            "steps": results,
            "commands": [f"git clone {bundle.name} solar_studio", "cd solar_studio/solar-site-layout", "UV_CACHE_DIR=$(mktemp -d) uv sync --frozen --python 3.12", ".venv/bin/solar-layout --data-dir <tmp> generate ../handoffs/module-01/fixtures/rectangle.request.json", ".venv/bin/solar-layout --data-dir <tmp> generate ../handoffs/module-01/fixtures/obstacle.request.json", ".venv/bin/solar-layout --data-dir <tmp> pitch ../handoffs/module-01/fixtures/pitch-3-4-5.request.json", ".venv/bin/python -m pytest -q"],
            "summary": "; ".join(f"{k}: exit {v['exit']}" + (f" -> {v.get('result')}" if "result" in v else "") + (f" ({v.get('tail')})" if "tail" in v else "") for k, v in results.items()),
            "private_paths_or_accounts_needed": "none (no Mac paths, accounts, weather API, LLM or CAD application)",
        }
        (DELIV / "reproduction.json").write_text(json.dumps(rep, indent=1))
        (DELIV / "reproduction-log.txt").write_text("\n".join(log))
        print(rep["summary"])
        return 0 if rep["passed"] and pkg["passed"] else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
