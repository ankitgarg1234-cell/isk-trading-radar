#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
parts = sorted((ROOT / "backtest/no_bear_parts").glob("part_*.pyfrag"))
if not parts:
    raise RuntimeError("no research backtest parts found")
source = "".join(p.read_text() for p in parts)
compile(source, "<no_bear_backtest>", "exec")
exec(compile(source, "<no_bear_backtest>", "exec"), globals(), globals())
