"""Temporary recovery helpers for a quota-blocked durable database.

The seed is supplied through an environment variable, never committed with
user-specific holdings. It is only applied when the canonical paper ledger is
absent, so normal persistent deployments are unaffected.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from .db import SessionLocal, ScoreBandExperiment, PaperAccount
from .score_band_experiment import VERSION, new_state


def ensure_recovery_seed() -> bool:
    raw = os.getenv("RADAR_RECOVERY_SEED_JSON", "").strip()
    if not raw:
        return False
    seed = json.loads(raw)
    with SessionLocal() as db:
        if db.query(ScoreBandExperiment).filter_by(version=VERSION).first():
            return False

        profile = str(seed.get("profile") or "MEDIUM").upper()
        state = new_state(profile)
        asof = str(seed["asof"])
        started_at = str(seed.get("started_at") or asof)
        starting_cash = float(seed.get("starting_cash") or 10000.0)
        cash = float(seed.get("cash") or 0.0)
        equity_target = float(seed.get("equity") or starting_cash)
        benchmark_return = float(seed.get("benchmark_return_pct") or 0.0)
        max_drawdown = float(seed.get("max_drawdown_pct") or 0.0)

        state["started_at"] = started_at
        state["last_cycle"] = asof
        state["last_market_open"] = True
        state["benchmark_start"] = 100.0
        state["benchmark_last"] = 100.0 * (1.0 + benchmark_return / 100.0)
        state["coverage"] = {
            "recovery_seed": 1,
            "recovery_source": "last_known_dashboard_snapshot",
        }
        state["recovery"] = {
            "active": True,
            "source_asof": asof,
            "note": "Durable history is preserved in the quota-blocked Neon project; reconstructed holdings are frozen from order generation until history is merged.",
        }

        book = state["variants"]["complete_strategy"]
        book["cash"] = cash
        book["positions"] = {}
        book["marks"] = {}
        book["pending"] = {}
        book["trades"] = []
        book["seen"] = {}

        for row in seed.get("positions") or []:
            symbol = str(row["symbol"]).upper()
            shares = float(row["shares"])
            avg_cost = float(row["avg_cost"])
            mark = float(row["mark"])
            rank = float(row.get("entry_rank") or 0.0)
            reason = str(row.get("reason") or "recovered snapshot")
            opened_at = str(row.get("opened_at") or started_at)
            fee_per_share = avg_cost * float(state["spec"]["fee_bps"]) / 10000.0
            book["positions"][symbol] = {
                "shares": shares,
                "avg_cost": avg_cost,
                "entry_fee_per_share": fee_per_share,
                # Exact historical stop/target geometry is inaccessible while
                # Neon is quota-blocked. These positions are explicitly frozen
                # by RECOVERY_READONLY_PAPER, so sentinel geometry cannot trade.
                "entry_stop": 0.01,
                "entry_target": 1_000_000_000.0,
                "entry_stretch_target": 1_000_000_000.0,
                "entry_horizon_days": 3650,
                "stop": 0.01,
                "harvested": False,
                "peak": max(avg_cost, mark),
                "opened_at": opened_at,
                "profit_steps": [],
                "recovery_frozen": True,
            }
            book["marks"][symbol] = mark
            book["seen"][symbol] = asof
            book["trades"].append({
                "symbol": symbol,
                "side": "BUY",
                "shares": shares,
                "price": avg_cost,
                "fees": shares * fee_per_share,
                "observed_at": opened_at,
                "reason": f"RECOVERED SNAPSHOT • {reason}",
                "deterministic_score": rank,
                "reconstructed": True,
            })

        if max_drawdown < 0 and (1.0 + max_drawdown / 100.0) > 0:
            book["peak_equity"] = equity_target / (1.0 + max_drawdown / 100.0)
        else:
            book["peak_equity"] = max(starting_cash, equity_target)
        book["max_drawdown_pct"] = max_drawdown
        book["samples"] = 1
        book["cash_pct_sum"] = (cash / equity_target * 100.0) if equity_target else 0.0
        book["fills"] = len(book["positions"])
        book["curve"] = [{
            "asof": asof,
            "equity": equity_target,
            "cash": cash,
            "positions": len(book["positions"]),
            "slot": asof[:14] + "00",
        }]

        db.add(ScoreBandExperiment(
            version=VERSION,
            state_json=json.dumps(state, default=str, separators=(",", ":")),
            updated_at=datetime.now(timezone.utc),
        ))
        account = db.query(PaperAccount).filter_by(account="Optimizer Paper").first()
        if not account:
            db.add(PaperAccount(
                account="Optimizer Paper",
                starting_cash=starting_cash,
                cash=cash,
                benchmark_symbol="^SP500TR",
                benchmark_start_price=100.0,
                benchmark_last_price=state["benchmark_last"],
                enabled=True,
                started_at=datetime.fromisoformat(started_at.replace("Z", "+00:00")),
                updated_at=datetime.now(timezone.utc),
            ))
        db.commit()
        print(
            f"RECOVERY_SEED_APPLIED positions={len(book['positions'])} "
            f"cash={cash:.2f} equity_snapshot={equity_target:.2f}",
            flush=True,
        )
        return True
