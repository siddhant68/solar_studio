"""Build references/manifest.json: reference identities, licences, build recipe and the
hash inventory of the built browser artifact that REA analysed (R01).

    python -I build_manifest.py DIST_DIR AGV_CHECKOUT PVPLANT_CHECKOUT REA_DIR BUILD_LOG OUT.json
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

KIND = {
    ".html": "html",
    ".js": "javascript",
    ".mjs": "javascript",
    ".wasm": "wasm",
    ".css": "css",
    ".json": "data",
    ".grid": "data",
    ".raster": "data",
    ".map": "source-map",
    ".woff2": "font",
    ".png": "image",
    ".jpg": "image",
    ".svg": "image",
    ".txt": "text",
}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def git(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, text=True).stdout.strip()


def main(dist: str, agv: str, pvplant: str, rea_dir: str, build_log: str, out: str) -> None:
    dist_p = Path(dist)
    files = []
    for f in sorted(p for p in dist_p.rglob("*") if p.is_file()):
        rel = f.relative_to(dist_p).as_posix()
        kind = KIND.get(f.suffix.lower(), "other") if f.name != "_headers" else "server-config"
        files.append({"path": rel, "kind": kind, "bytes": f.stat().st_size, "sha256": sha(f)})
    counts: dict[str, int] = {}
    for f in files:
        counts[f["kind"]] = counts.get(f["kind"], 0) + 1
    agv_p, pv_p = Path(agv), Path(pvplant)
    rea_pkg = json.loads((Path(rea_dir) / "node_modules" / "rea-agents" / "package.json").read_text())
    lock = json.loads((Path(rea_dir) / "package-lock.json").read_text())
    manifest = {
        "generated_by": "references/probes/build_manifest.py",
        "references": [
            {
                "role": "primary_browser_artifact (REA target)",
                "repository": "https://github.com/peterklingelhofer/agrivoltaic-garden-planner",
                "commit_pinned": "43118b3939a91df5ba641a3b0470022ff7ecc5c7",
                "commit_checked_out": git(agv_p, "rev-parse", "HEAD"),
                "commit_date": git(agv_p, "log", "-1", "--format=%cI"),
                "substitution": None,
                "licences": {
                    "code": "Apache-2.0 (LICENSE)",
                    "docs_and_data": "CC BY 4.0 (LICENSE-DOCS) for docs/, data/, public/data/",
                    "third_party_data": "terms named in public/data/manifest.json (NOTICE)",
                    "LICENSE_sha256": sha(agv_p / "LICENSE"),
                    "LICENSE-DOCS_sha256": sha(agv_p / "LICENSE-DOCS"),
                    "NOTICE_sha256": sha(agv_p / "NOTICE"),
                },
                "build_recipe": {
                    "commands": [
                        "rustup target add wasm32-unknown-unknown",
                        "bun install --frozen-lockfile",
                        "VITE_AGENT=off bun run build   # = cargo build --release --target wasm32-unknown-unknown (agv-sim) && cp wasm to public/ && tsc -b && vite build && node scripts/render-docs.mjs",
                    ],
                    "not_run": ["build:deploy", "deploy", "fetch-agent-model", "secret:*", "fetch-layers", "wrangler *"],
                    "agent_panel": "off (VITE_AGENT=off; production build default)",
                    "tool_versions": {
                        "bun": subprocess.run(["bun", "--version"], capture_output=True, text=True).stdout.strip(),
                        "bun_declared_packageManager": "bun@1.4.2",
                        "rustc": subprocess.run(["rustc", "--version"], capture_output=True, text=True).stdout.strip(),
                        "cargo": subprocess.run(["cargo", "--version"], capture_output=True, text=True).stdout.strip(),
                        "node_used_by_package_scripts": subprocess.run(["node", "--version"], capture_output=True, text=True).stdout.strip(),
                    },
                    "build_log_sha256": sha(Path(build_log)),
                    "bun_lock_sha256": sha(agv_p / "bun.lock"),
                },
                "built_artifact": {
                    "description": "local production build (dist/) of the pinned commit; this exact directory was analysed by REA and served on http://127.0.0.1:4173 by python -m http.server for runtime scenarios",
                    "root_sha256_reported_by_rea": "4e9098e6562b377c1ecfa439b323a684238d95d1ce9acbc4ded47de4683c413f",
                    "file_count": len(files),
                    "kind_counts": counts,
                    "source_maps_present": counts.get("source-map", 0) > 0,
                    "files": files,
                },
            },
            {
                "role": "secondary_source_reference (ordinary source reading, not REA)",
                "repository": "https://github.com/JavierBrana/PVPlant",
                "commit_pinned": "7852ee562c92706e5e3e5d095cefccd5070b18d3",
                "commit_checked_out": git(pv_p, "rev-parse", "HEAD"),
                "commit_date": git(pv_p, "log", "-1", "--format=%cI"),
                "licence_observation": "PVPlantRack.py and PVPlantPlacement.py headers: GNU LGPL version 2 or later, referring to 'the LICENCE text file'; no LICENCE/LICENSE/COPYING file exists at this commit (checked); no blanket repository licence is declared here",
                "files_read": {
                    "PVPlantRack.py": sha(pv_p / "PVPlantRack.py"),
                    "PVPlantPlacement.py": sha(pv_p / "PVPlantPlacement.py"),
                },
                "code_reused": "none (concepts only; no code copied or adapted)",
                "freecad_installed": False,
            },
            {
                "role": "numerical_reference",
                "repository": "https://github.com/pvlib/pvlib-python",
                "licence": "BSD-3-Clause",
                "used": "not installed or executed: the Module 01 pitch calculator takes a supplied solar elevation and needs no ephemeris; pvlib is recorded for the later energy module",
            },
        ],
        "tools": {
            "rea": {
                "package": rea_pkg["name"],
                "version": rea_pkg["version"],
                "integrity": lock["packages"]["node_modules/rea-agents"]["integrity"],
                "license": rea_pkg.get("license"),
                "engines": rea_pkg.get("engines"),
                "runtime": "node v24.22.1 (nodejs.org linux-x64 tarball, SHA256SUMS verified), isolated in a tools folder; no MCP client registration changed; `rea setup` not run",
                "install_scripts_not_run": ["frida (npm install-scripts gate)"],
            },
            "playwright": "1.62.0 (preinstalled Node package) with Chromium 153.0.8010.12 (/opt/pw-browsers/chromium-1243)",
        },
    }
    Path(out).write_text(json.dumps(manifest, indent=1))
    print(json.dumps(counts))


if __name__ == "__main__":
    main(*sys.argv[1:7])
