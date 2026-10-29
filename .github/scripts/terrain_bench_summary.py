"""Print the TD02 benchmark result as Markdown (standard library only).

    python3 .github/scripts/terrain_bench_summary.py TERRAIN_BENCHMARKS.json
"""

import json
import sys

r = json.load(open(sys.argv[1]))
t, p, m = r["td02"], r["phases"], r["machine"]
print("## Terrain benchmark TD02\n")
print(f"**{'PASS' if t['pass'] else 'FAIL'}**: placement {t['process_wall_s']} s, peak {t['peak_tree_rss_mib']} MiB (targets {t['wall_target_s']} s, {t['memory_target_mib']} MiB)\n")
print(f"- terrain import: {p['terrain_import']['wall_s']} s, {p['terrain_import']['peak_tree_rss_mib']} MiB (reported, no T1 target)")
print(f"- cold workflow: {p['cold_workflow']['wall_s']} s, {p['cold_workflow']['peak_tree_rss_mib']} MiB (reported, no T1 target)")
print(f"- machine: {m['cpu_model']}, {m['logical_cpus']} logical CPUs, {m['memory_total_mib']} MiB, {m['os']}")
