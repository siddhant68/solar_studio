"""Summarise one REA `capture_browser_scenario` Evidence JSON file.

The Evidence is read as data only: nothing extracted from it is executed. The probe
writes the captured PNG screenshots (after checking each one against the SHA-256 that
REA recorded), the captured DOM text, and a JSON summary of step outcomes, storage
fingerprints and the reference app's `readout-array-*` / `control-array-*` values found
in the captured DOM.

    python -I extract_rea_scenario.py EVIDENCE.json OUT_DIR
"""

from __future__ import annotations

import base64
import hashlib
import html
import json
import re
import sys
from pathlib import Path

READOUT = re.compile(
    r'data-testid="(readout-array-[a-z-]+)"[^>]*>(.*?)</', re.S
)
CONTROL = re.compile(r"<input[^>]*>", re.S)
ATTR = re.compile(r'([a-zA-Z-]+)="([^"]*)"')


def _controls(dom: str) -> dict[str, str | None]:
    found: dict[str, str | None] = {}
    for tag in CONTROL.findall(dom):
        attrs = dict(ATTR.findall(tag))
        test_id = attrs.get("data-testid", "")
        if test_id.startswith("control-array-"):
            found[test_id] = attrs.get("value")
    return found


def _readouts(dom: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for test_id, body in READOUT.findall(dom):
        text = re.sub(r"<[^>]+>", " ", body)
        out[test_id] = html.unescape(" ".join(text.split()))
    return out


def main(evidence_path: str, out_dir: str) -> int:
    evidence = json.loads(Path(evidence_path).read_text())
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result = evidence["normalized_result"]
    summary: dict[str, object] = {
        "evidence_id": evidence["evidence_id"],
        "provider": evidence["provider"],
        "predicate_type": evidence["predicate_type"],
        "browser": result["browser"],
        "duration_ms": result["duration_ms"],
        "completeness": result["completeness"],
        "steps": [],
    }
    steps = []
    for step in result["steps"]:
        record: dict[str, object] = {
            "index": step["step_index"],
            "step_id": step["step_id"],
            "action": step["action"],
            "status": step["status"],
            "error": step["error"],
            "after_url": step["after_url"]["url"],
        }
        artifacts = step["artifacts"]
        shot = artifacts.get("screenshot", {})
        if shot.get("state") == "captured":
            data = base64.b64decode(shot["value"]["data_base64"])
            digest = hashlib.sha256(data).hexdigest()
            if digest != shot["value"]["sha256"]:
                raise SystemExit(f"screenshot digest mismatch in step {step['step_id']}")
            name = f"{step['step_index']:02d}-{step['step_id']}.png"
            (out / name).write_bytes(data)
            record["screenshot"] = {"file": name, "sha256": digest, "bytes": len(data)}
        dom = artifacts.get("dom", {})
        if dom.get("state") == "captured":
            text = dom["value"]["text"]
            name = f"{step['step_index']:02d}-{step['step_id']}.dom.html"
            (out / name).write_text(text)
            record["dom"] = {"file": name, "sha256": dom["value"]["sha256"]}
            record["readouts"] = _readouts(text)
            record["controls"] = _controls(text)
        storage = artifacts.get("storage", {})
        if storage.get("state") == "captured":
            value = storage["value"]
            record["storage"] = {
                "local_storage": [
                    {k: v for k, v in entry.items() if k != "value"}
                    for entry in value.get("local_storage", [])
                ],
                "session_storage_entries": len(value.get("session_storage", [])),
                "cookies": len(value.get("cookies", [])),
            }
        steps.append(record)
    summary["steps"] = steps
    summary["limitations"] = result.get("limitations", [])
    (out / "summary.json").write_text(json.dumps(summary, indent=1, sort_keys=True))
    failed = [s["step_id"] for s in steps if s["status"] != "completed"]
    print(json.dumps({"steps": len(steps), "failed": failed, "out": str(out)}))
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
