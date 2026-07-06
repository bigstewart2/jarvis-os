#!/usr/bin/env python3
"""Stand-in for the `claude` CLI in tests. Behavior controlled via env vars:

STUB_CLI_MODE=success|failure (default: success)
STUB_CLI_PID_FILE=<path> (optional) — if set, spawns a child process and
    writes this process's PID and the child's PID to the file, one per line,
    for tests that verify no orphaned processes survive a kill.
"""
import json
import os
import subprocess
import sys


def emit(obj: dict) -> None:
    print(json.dumps(obj), flush=True)


def main() -> None:
    mode = os.environ.get("STUB_CLI_MODE", "success")
    pid_file = os.environ.get("STUB_CLI_PID_FILE")

    if pid_file:
        child = subprocess.Popen(["sleep", "60"])
        with open(pid_file, "w") as f:
            f.write(f"{os.getpid()}\n{child.pid}\n")

    emit({"type": "system", "subtype": "init"})
    emit({"type": "assistant", "message": {"content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": "foo.py"}}]}})
    emit({"type": "assistant", "message": {"content": [{"type": "text", "text": "Working on it."}]}})
    print("not valid json at all", flush=True)

    if os.environ.get("STUB_CLI_SLOW") == "1":
        import time
        time.sleep(120)

    if mode == "failure":
        emit({
            "type": "result", "subtype": "error_max_turns", "result": "failed",
            "num_turns": 1, "duration_ms": 10, "total_cost_usd": 0.01,
        })
        sys.exit(1)

    emit({
        "type": "result", "subtype": "success", "result": "Done.",
        "num_turns": 2, "duration_ms": 500, "total_cost_usd": 0.02,
    })
    sys.exit(0)


if __name__ == "__main__":
    main()
