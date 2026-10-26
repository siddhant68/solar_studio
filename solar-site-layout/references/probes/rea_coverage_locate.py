"""Locate executed code for a control change in REA `observe_web_execution` Evidence.

Reads the Evidence as data (nothing is executed). For every function REA reports as
executed (count > 0) in the selected script, it checks whether the function's source
range, taken from the source text REA retained with the same Evidence, contains any of
the given tokens. Offsets are UTF-16 code units, as REA records them.

    python -I rea_coverage_locate.py EVIDENCE.json IDLE_EVIDENCE.json OUT.json TOKEN...
"""

from __future__ import annotations

import json
import sys


def utf16_slice(text: str, start: int, end: int) -> str:
    data = text.encode("utf-16-le")
    return data[2 * start : 2 * end].decode("utf-16-le", errors="replace")


def executed(evidence: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for script in evidence["normalized_result"]["coverage"]["scripts"]:
        rows = []
        for fn in script["functions"]:
            r0 = fn["ranges"][0]
            if r0["count"] > 0:
                rows.append({"name": fn["name"], "start": r0["start_offset"], "end": r0["end_offset"], "count": r0["count"]})
        out[script["reported_url"]] = rows
    return out


def main(path: str, idle_path: str, out_path: str, tokens: list[str]) -> None:
    ev = json.loads(open(path).read())
    idle = json.loads(open(idle_path).read())
    sources = {s["url"]: s for s in ev["normalized_result"]["sources"] if s["source"].get("state") == "captured"}
    idle_exec = executed(idle)
    report = {
        "evidence_id": ev["evidence_id"],
        "idle_evidence_id": idle["evidence_id"],
        "provider": ev["provider"],
        "window": ev["normalized_result"]["window"],
        "idle_executed_function_counts": {u: len(v) for u, v in idle_exec.items()},
        "scripts": [],
    }
    for url, rows in executed(ev).items():
        src = sources.get(url)
        entry = {"url": url, "executed_functions": len(rows), "source_sha256": src["source"]["sha256"] if src else None, "matches": []}
        if src:
            text = src["source"]["text"]
            for row in rows:
                body = utf16_slice(text, row["start"], row["end"])
                hits = sorted({t for t in tokens if t in body})
                # keep the innermost functions: skip very large ranges (module wrappers)
                if hits and row["end"] - row["start"] < 20_000:
                    i = min(body.find(t) for t in hits)
                    entry["matches"].append({**row, "tokens": hits, "excerpt": body[max(0, i - 160) : i + 240]})
        entry["matches"].sort(key=lambda r: (r["start"], r["end"]))
        report["scripts"].append(entry)
    open(out_path, "w").write(json.dumps(report, indent=1))
    for s in report["scripts"]:
        print(s["url"], s["executed_functions"], "matching:", len(s["matches"]))
        for m in s["matches"][:40]:
            print("  ", m["name"] or "<anon>", m["start"], m["end"], m["count"], m["tokens"])


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4:])
