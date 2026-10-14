"""Offline tests for GEM unattended research worker."""
import sqlite3
from pathlib import Path
from unittest.mock import patch
from scripts.gem_autonomous_research_worker import execute, TASKS

def test_bounded_worker_advances_and_records_failures(tmp_path: Path):
    with sqlite3.connect(tmp_path / "progress.sqlite") as conn:
        with patch("scripts.gem_autonomous_research_worker.subprocess.run") as run:
            run.return_value.returncode = 1
            run.return_value.stdout = ""
            run.return_value.stderr = "diagnostic failed"
            report = execute(conn, output=tmp_path / "out")
        assert len(report["results"]) == len(TASKS)
        assert report["results"][0]["status"] == "FAIL"
        assert all(r["status"] == "BLOCKED" for r in report["results"][1:])
        assert conn.execute("SELECT count(*) FROM runs").fetchone()[0] == len(TASKS)
        assert report["release"] == "DATA_HOLD"
        assert report["trading_authorized"] is False
        assert report["source_certified"] is False
        assert (tmp_path / "out" / "worker-report.json").is_file()
