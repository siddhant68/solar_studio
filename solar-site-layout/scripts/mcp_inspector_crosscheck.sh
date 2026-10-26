#!/usr/bin/env bash
# Second, independently implemented MCP client: the MCP Inspector CLI (TypeScript SDK).
#   scripts/mcp_inspector_crosscheck.sh INSPECTOR_DIR OUT_DIR
# INSPECTOR_DIR holds an npm install of @modelcontextprotocol/inspector (pinned 2.12.0).
# Every call goes through scripts/mcp_wire_tap.py so the JSON-RPC exchange is retained.
set -euo pipefail
here="$(cd "$(dirname "$0")/.." && pwd)"
insp="$1"; out="$2"
mkdir -p "$out"
py="$here/.venv/bin/python"
fx="$here/../handoffs/module-01/fixtures"
pitch="$("$py" -c "import json,sys;print(json.dumps(json.load(open(sys.argv[1]))))" "$fx/pitch-3-4-5.request.json")"
rect="$("$py" -c "import json,sys;print(json.dumps(json.load(open(sys.argv[1]))))" "$fx/rectangle.request.json")"
cd "$insp"
run() {
  local name="$1"; shift
  set +e
  MCP_CATALOG_PATH="$out/catalog.json" timeout 120 npx --no-install mcp-inspector --cli "$@" -- \
    "$py" "$here/scripts/mcp_wire_tap.py" "$out/wire-$name.jsonl" -- "$py" -m solar_layout.mcp_server --data-dir "$out/data" \
    > "$out/$name.json" 2> "$out/$name.stderr"
  echo "$name exit=$?"
  set -e
}
run tools-list --method tools/list
run call-pitch --method tools/call --tool-name calculate_row_pitch --tool-arg "request=$pitch"
run call-generate --method tools/call --tool-name generate_layout --tool-arg "request=$rect"
run call-bad-items --method tools/call --tool-name get_layout_items --tool-arg "result_id=res_000000000000000000000000"
