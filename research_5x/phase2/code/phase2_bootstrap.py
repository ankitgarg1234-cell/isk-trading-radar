"""Resolve the frozen engine in either the local workspace or repository layout."""
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'research_5x/code'))
import run_research as e
if not e.REPO.exists() and (ROOT/'backtests/staged/wf3_prices.json.gz').exists():
    e.REPO = ROOT
OUT = ROOT/'research_5x/phase2/2026-10-11_earnings_acceleration'
