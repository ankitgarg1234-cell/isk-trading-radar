"""Bounded unattended GEM research diagnostics. Never approves sources or trades."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import subprocess
import sys

TASKS = ("calendar", "benchmark", "prices", "sec", "membership", "actions")
COMMANDS = {
    "calendar": [sys.executable, "-m", "scripts.gem_source_fastpath_ci"],
    "benchmark": [sys.executable, "-m", "scripts.gem_source_fastpath_ci"],
}
def initialize(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS runs(
        id INTEGER PRIMARY KEY, task TEXT NOT NULL, started TEXT NOT NULL,
        finished TEXT NOT NULL, status TEXT NOT NULL, detail TEXT NOT NULL,
        sha256 TEXT NOT NULL)""")
    conn.commit()

def execute(conn, *, output: Path, timeout=180):
    """Run independent bounded diagnostics, record failures, then advance."""
    initialize(conn)
    output.mkdir(parents=True, exist_ok=True)
    results = []
    for task in TASKS:
        started = datetime.now(timezone.utc).isoformat()
        command = COMMANDS.get(task)
        if command:
            try:
                args = command + ["--outdir", str(output / task)]
                result = subprocess.run(args, capture_output=True, text=True,
                                        timeout=timeout, check=False)
                status = "PASS_RESEARCH_ONLY" if result.returncode == 0 else "FAIL"
                detail = (result.stdout + "\n" + result.stderr)[-2000:]
            except subprocess.TimeoutExpired:
                status, detail = "TIMEOUT", "Bounded execution timed out"
            except OSError as exc:
                status, detail = "FAIL", type(exc).__name__
        else:
            status, detail = "BLOCKED", "No approved bounded executor configured"
        finished = datetime.now(timezone.utc).isoformat()
        digest = hashlib.sha256(f"{task}|{started}|{finished}|{status}|{detail}".encode()).hexdigest()
        conn.execute("INSERT INTO runs(task,started,finished,status,detail,sha256) VALUES(?,?,?,?,?,?)",
                     (task,started,finished,status,detail,digest))
        conn.commit()
        results.append(dict(task=task, started=started, finished=finished,
                            status=status, detail=detail, sha256=digest))
    report = dict(schema="gem-autonomous-research-v1", generated_at=datetime.now(timezone.utc).isoformat(),
                  release="DATA_HOLD", trading_authorized=False, source_certified=False,
                  results=results)
    (output / "worker-report.json").write_text(json.dumps(report, indent=2))
    return report

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=Path("gem-worker-output"))
    parser.add_argument("--database", type=Path, default=Path("gem-worker-output/progress.sqlite"))
    args = parser.parse_args()
    args.database.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(args.database) as conn:
        report = execute(conn, output=args.output)
    print(json.dumps({"release": report["release"], "statuses": {
        row["task"]: row["status"] for row in report["results"]}}, sort_keys=True))

if __name__ == "__main__":
    main()
