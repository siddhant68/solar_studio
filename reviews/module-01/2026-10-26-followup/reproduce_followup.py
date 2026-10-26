"""Portable follow-up checks: source bindings, corrupt power, four-process publication.

Run using the application's installed Python environment, with --repo pointing to the
repository root and --out to a new scratch directory. This does not replace the full
pytest/browser/MCP suite. All generated data stays outside the source tree in a temporary
directory; only the JSON observations are retained under --out.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import copy
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

from solar_layout.service import SolarService
from solar_layout.verify import verify_records


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--repo", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    repo = args.repo.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((repo / "solar-site-layout/evidence/acceptance/run-meta.json").read_text())

    def git(*argv: str) -> str:
        return subprocess.check_output(["git", *argv], cwd=repo, text=True).strip()

    observations = {
        "head": git("rev-parse", "HEAD"),
        "source_commit_in_acceptance": metadata["source_commit"],
        "tree_bindings": {
            path: {"recorded": digest, "actual": git("rev-parse", "HEAD:" + path)}
            for path, digest in metadata["source_tree_ids"].items()
        },
    }
    request = json.loads((repo / "handoffs/module-01/fixtures/rectangle.request.json").read_text())
    with tempfile.TemporaryDirectory(prefix="solar-followup-") as temp:
        service = SolarService(temp)
        generated = service.generate_layout(request=request)
        result_id = generated["result_id"]
        stored = service.store.get_result_row(result_id)
        tables = list(service.store.iter_records(result_id, "tables"))
        modules = list(service.store.iter_records(result_id, "modules"))
        altered = copy.deepcopy(modules)
        altered[0]["power_wp"] = 123456
        verification = verify_records(request, stored["summary"], tables, altered)
        observations["corrupt_power_rejected"] = not verification["ok"]
        observations["corrupt_power_failed_checks"] = [
            key for key, result in verification["checks"].items() if not result["ok"]
        ]

        # Four independent Python processes publish the same initially unissued bundle.
        # They share the SQLite store and export root, with no injected scheduling hooks.
        program = (
            "import json,sys; from solar_layout.service import SolarService; "
            "s=SolarService(sys.argv[1]); "
            "print(json.dumps(s.export_layout(sys.argv[2], 'bundle')))"
        )

        def publish(_: int) -> dict:
            process = subprocess.run(
                [sys.executable, "-c", program, temp, result_id],
                cwd=repo / "solar-site-layout",
                capture_output=True,
                text=True,
                timeout=90,
            )
            return {
                "returncode": process.returncode,
                "result": json.loads(process.stdout) if process.returncode == 0 else None,
                "stderr": process.stderr,
            }

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            calls = list(pool.map(publish, range(4)))
        observations["four_process_calls"] = calls
        successful = [call["result"] for call in calls if call["returncode"] == 0]
        observations["four_process_passed"] = (
            len(successful) == 4
            and len({result["sha256"] for result in successful}) == 1
            and len({result["path"] for result in successful}) == 1
        )
        if successful:
            artifact = service.store.export_root / successful[0]["path"]
            observations["published_bytes_match"] = (
                hashlib.sha256(artifact.read_bytes()).hexdigest() == successful[0]["sha256"]
            )
        else:
            observations["published_bytes_match"] = False

    observations["passed"] = (
        all(item["recorded"] == item["actual"] for item in observations["tree_bindings"].values())
        and observations["corrupt_power_rejected"]
        and observations["four_process_passed"]
        and observations["published_bytes_match"]
    )
    destination = args.out / "portable-followup.json"
    destination.write_text(json.dumps(observations, indent=2) + "\n")
    print(json.dumps({"passed": observations["passed"], "evidence": str(destination)}))
    if not observations["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
