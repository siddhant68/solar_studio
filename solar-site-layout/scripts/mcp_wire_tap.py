"""Transparent stdio relay that records every MCP JSON-RPC line in both directions.

    python mcp_wire_tap.py LOG.jsonl -- COMMAND [ARGS...]

The MCP client launches this script as its "server"; the script launches the real
server and copies bytes unchanged, appending one record per line to LOG.jsonl:
{"t": seconds, "dir": "client->server" | "server->client", "message": <parsed JSON>}.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time


def main() -> int:
    log_path = sys.argv[1]
    assert sys.argv[2] == "--"
    cmd = sys.argv[3:]
    child = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    t0 = time.monotonic()
    lock = threading.Lock()
    log = open(log_path, "a", buffering=1)

    def record(direction: str, line: bytes) -> None:
        try:
            msg = json.loads(line)
        except ValueError:
            msg = {"unparsed": line.decode("utf-8", "replace")}
        with lock:
            log.write(json.dumps({"t": round(time.monotonic() - t0, 6), "dir": direction, "message": msg}) + "\n")

    def pump_in() -> None:
        for line in sys.stdin.buffer:
            record("client->server", line)
            child.stdin.write(line)
            child.stdin.flush()
        child.stdin.close()

    def pump_out() -> None:
        for line in child.stdout:
            record("server->client", line)
            sys.stdout.buffer.write(line)
            sys.stdout.buffer.flush()

    threads = [threading.Thread(target=pump_in, daemon=True), threading.Thread(target=pump_out, daemon=True)]
    for th in threads:
        th.start()
    code = child.wait()
    threads[1].join(timeout=5)
    log.close()
    return code


if __name__ == "__main__":
    sys.exit(main())
