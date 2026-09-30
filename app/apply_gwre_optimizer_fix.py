#!/usr/bin/env python3
"""Apply the GWRE optimizer revalidation fix to isk-trading-radar.

Base verified against main commit:
63e67817cd633ff32af425e1dd8a3e023bb6695f

Run from the repository root:
    python apply_gwre_optimizer_fix.py
    pytest tests/test_optimizer.py
"""
from __future__ import annotations

from pathlib import Path
import shutil

ROOT = Path.cwd()


def replace_once(path: str, old: str, new: str, marker: str) -> None:
    p = ROOT / path
    if not p.exists():
        raise SystemExit(f"Missing expected file: {path}")
    text = p.read_text(encoding="utf-8")
    if marker in text:
        print(f"SKIP {path}: already patched ({marker})")
        return
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}; repo may have changed. No write performed for this step.")
    backup = p.with_suffix(p.suffix + ".gwre.bak")
    if not backup.exists():
        shutil.copy2(p, backup)
    p.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"PATCHED {path}")


# 1) Scanner: retain a separate policy/config fingerprint so a BUY->BUY ticker
# is reconsidered when portfolio eligibility changes.
replace_once(
    "app/scanner.py",
    '''        self._paper_entry_state: dict[str, tuple] = {}\n        self._last_strategic_enrich_at: datetime | None = None\n''',
    '''        self._paper_entry_state: dict[str, tuple] = {}\n        # Portfolio eligibility/config state is deliberately separate from the\n        # per-symbol BUY state. A service restart or a material optimizer-policy\n        # change must force one full Top-20 re-evaluation even when a stock stays\n        # BUY -> BUY (the GWRE missed-entry failure mode).\n        self._paper_optimizer_policy_state: str | None = None\n        self._last_strategic_enrich_at: datetime | None = None\n''',
    "_paper_optimizer_policy_state",
)

replace_once(
    "app/scanner.py",
    '''    def _paper_entry_event(self, full: dict) -> bool:\n''',
    '''    def _paper_optimizer_policy_fingerprint(self) -> str:\n        """Fingerprint every rule that can change paper-entry eligibility.\n\n        This is intentionally independent of ticker signal transitions. Removing\n        a sector/tier restriction, changing risk profile or changing optimizer\n        thresholds must invalidate the prior portfolio selection even if GWRE (or\n        any other candidate) remains BUY before and after the change.\n        """\n        with SessionLocal() as db:\n            pref = db.query(PortfolioPreference).filter(PortfolioPreference.account == "Main").first()\n            profile = normalise_profile(pref.risk_profile if pref else "MEDIUM")\n        material = {\n            "policy_version": "eligibility-v2-no-sector-no-tier",\n            "risk_profile": profile,\n            "visible_limit": settings.optimizer_visible_limit,\n            "shortlist_limit": settings.optimizer_shortlist_limit,\n            "target_positions": settings.optimizer_target_positions,\n            "max_positions": settings.optimizer_max_positions,\n            "min_rank_score": settings.optimizer_min_rank_score,\n            "rotation_gap": settings.optimizer_rotation_gap,\n            "rotation_yield_gap": settings.optimizer_rotation_yield_gap,\n            "paper_trade_cost_bps": settings.paper_trade_cost_bps,\n            "investable_entry_actions": sorted(INVESTABLE_ENTRY_ACTIONS),\n            # Explicitly encode the current policy: these legacy constraints are gone.\n            "sector_position_cap": None,\n            "per_tier_max_positions": None,\n        }\n        return hashlib.sha1(json.dumps(material, sort_keys=True, default=str).encode("utf-8")).hexdigest()\n\n    def _paper_optimizer_invalidation_event(self) -> bool:\n        """Return True once when optimizer eligibility/config becomes stale.\n\n        The first open-market scan after a service restart intentionally returns\n        True. That one harmless recheck prevents stale portfolio decisions after a\n        deployment that changes eligibility rules.\n        """\n        current = self._paper_optimizer_policy_fingerprint()\n        previous = self._paper_optimizer_policy_state\n        self._paper_optimizer_policy_state = current\n        return previous != current\n\n    def _paper_entry_event(self, full: dict) -> bool:\n''',
    "def _paper_optimizer_policy_fingerprint",
)

replace_once(
    "app/scanner.py",
    '''        ok = 0\n        errors: list[str] = []\n        paper_entry_event = False\n        paper_event_symbols: list[str] = []\n''',
    '''        ok = 0\n        errors: list[str] = []\n        # Portfolio-rule/config changes are first-class optimizer events. This is\n        # what makes an already-actionable BUY such as GWRE get reconsidered after\n        # a blocking restriction is removed; no BUY -> BUY transition is required.\n        optimizer_policy_event = self._paper_optimizer_invalidation_event()\n        paper_entry_event = optimizer_policy_event\n        paper_event_symbols: list[str] = []\n''',
    "optimizer_policy_event = self._paper_optimizer_invalidation_event()",
)

replace_once(
    "app/scanner.py",
    '''            # Entry decisions are event-driven: all newly actionable names from\n            # this completed scan are coalesced into one optimizer run.  Broader\n            # portfolio rotation remains on the daily cadence inside paper_engine.\n            run_paper_cycle(self.provider, entry_event=paper_entry_event)\n''',
    '''            # Entry decisions are event-driven. A run is triggered by either a\n            # material ticker event OR a portfolio-eligibility/config invalidation.\n            # The paper engine then reloads and re-ranks the complete current Top 20,\n            # so a BUY does not need to leave BUY and become BUY again to be seen.\n            # Broader portfolio rotation remains on the daily cadence.\n            run_paper_cycle(self.provider, entry_event=paper_entry_event)\n''',
    "portfolio-eligibility/config invalidation",
)

replace_once(
    "app/scanner.py",
    '''            "paper_entry_event": paper_entry_event,\n            "paper_event_symbols": paper_event_symbols,\n''',
    '''            "paper_entry_event": paper_entry_event,\n            "paper_optimizer_invalidated": optimizer_policy_event,\n            "paper_event_symbols": paper_event_symbols,\n''',
    '"paper_optimizer_invalidated": optimizer_policy_event',
)


# 2) Optimizer: every visible Top-20 name gets an explicit portfolio decision.
# No sector cap and no per-tier max-two gate are introduced.
replace_once(
    "app/portfolio_engine.py",
    '''    rows.sort(key=lambda r: (r["rank_score"], r["expected_yield_pct"]), reverse=True)\n    for i, r in enumerate(rows, 1):\n        r["market_rank"] = i\n        r["bucket"] = "RESERVE"\n        r["optimizer_action"] = "PASS"\n\n    visible = rows[:max(1, visible_limit)]\n    shortlist = visible[:max(1, min(shortlist_limit, len(visible)))]\n    for r in shortlist:\n        r["bucket"] = "SHORTLIST"\n        r["optimizer_action"] = "WATCH CLOSELY"\n    for r in visible:\n        if r["owned"]:\n            r["bucket"] = "PORTFOLIO"\n            r["optimizer_action"] = "HOLD / MANAGE"\n\n    owned_rows = [r for r in rows if r["owned"]]\n\n    selected_new = []\n    # Aim for six holdings, never exceed seven, and never force weak candidates.\n    open_slots = max(0, min(target_positions, max_positions) - len(owned))\n    for r in shortlist:\n        if open_slots <= 0:\n            break\n        if r["owned"]:\n            continue\n        if r["entry_signal"] not in INVESTABLE_ENTRY_ACTIONS:\n            continue\n        if r["rank_score"] < min_rank_score or r["risk_fit"] == "ABOVE TARGET":\n            continue\n        r["bucket"] = "INVEST NOW"\n        r["optimizer_action"] = r["entry_signal"]\n        selected_new.append(r)\n        open_slots -= 1\n''',
    '''    rows.sort(key=lambda r: (r["rank_score"], r["expected_yield_pct"]), reverse=True)\n    effective_shortlist_limit = max(1, min(shortlist_limit, max(1, visible_limit)))\n    for i, r in enumerate(rows, 1):\n        r["market_rank"] = i\n        r["bucket"] = "RESERVE"\n        r["optimizer_action"] = "PASS"\n        r["decision_reason"] = f"PASS — Rank #{i}; Top-{effective_shortlist_limit} shortlist required"\n\n    visible = rows[:max(1, visible_limit)]\n    shortlist = visible[:max(1, min(shortlist_limit, len(visible)))]\n    for r in shortlist:\n        r["bucket"] = "SHORTLIST"\n        r["optimizer_action"] = "PASS"\n        r["decision_reason"] = "PASS — awaiting portfolio eligibility checks"\n    for r in visible:\n        if r["owned"]:\n            r["bucket"] = "PORTFOLIO"\n            r["optimizer_action"] = "HOLD / MANAGE"\n            r["decision_reason"] = "HOLD / MANAGE — already held in the portfolio"\n\n    owned_rows = [r for r in rows if r["owned"]]\n\n    selected_new = []\n    # Aim for six holdings, never exceed seven, and never force weak candidates.\n    # Every shortlist row gets BUY or an explicit PASS reason; no silent BUYs.\n    open_slots = max(0, min(target_positions, max_positions) - len(owned))\n    for r in shortlist:\n        if r["owned"]:\n            continue\n        if r["entry_signal"] not in INVESTABLE_ENTRY_ACTIONS:\n            r["decision_reason"] = f"PASS — current entry signal {r['entry_signal'] or 'NONE'} is not investable"\n            continue\n        if r["rank_score"] < min_rank_score:\n            r["decision_reason"] = f"PASS — portfolio priority {r['rank_score']:.1f} is below {min_rank_score:.1f} minimum"\n            continue\n        if r["risk_fit"] == "ABOVE TARGET":\n            r["decision_reason"] = "PASS — stock risk is above the selected portfolio risk profile"\n            continue\n        if open_slots <= 0:\n            r["decision_reason"] = f"PASS — target portfolio slots already allocated ({min(target_positions, max_positions)} target)"\n            continue\n        r["bucket"] = "INVEST NOW"\n        r["optimizer_action"] = r["entry_signal"]\n        r["decision_reason"] = f"{r['entry_signal']} — selected at portfolio rank #{r['market_rank']}"\n        selected_new.append(r)\n        open_slots -= 1\n''',
    "decision_reason",
)

replace_once(
    "app/portfolio_engine.py",
    '''                    candidate["bucket"] = "ROTATE IN"\n                    candidate["optimizer_action"] = "ROTATE"\n                    rotations.append({\n''',
    '''                    candidate["bucket"] = "ROTATE IN"\n                    candidate["optimizer_action"] = "ROTATE"\n                    candidate["decision_reason"] = f"ROTATE — stronger than {held['symbol']} by {rank_gap:.1f} priority pts and {yield_gap:.1f} expected-return pts"\n                    rotations.append({\n''',
    'candidate["decision_reason"] = f"ROTATE',
)


# 3) Regression tests: GWRE-style BUY->BUY plus explicit PASS visibility.
test_path = ROOT / "tests/test_optimizer.py"
test_text = test_path.read_text(encoding="utf-8")
marker = "def test_gwre_style_policy_change_rechecks_without_buy_state_transition"
if marker not in test_text:
    addition = r'''\n\n\ndef test_optimizer_has_no_per_tier_max_two_cap():\n    analyses = {}\n    for i in range(6):\n        p = payload(f"TIER{i}", score=95-i, sector="Technology", expected=35-i)\n        p["tier"] = "A"\n        analyses[p["symbol"]] = p\n    plan = build_optimizer_plan(\n        analyses, profile="HIGH", visible_limit=20, shortlist_limit=10,\n        target_positions=6, max_positions=7, min_rank_score=62\n    )\n    assert len(plan["selected_new"]) == 6\n\n\ndef test_actionable_visible_candidate_always_has_buy_or_explicit_pass_reason():\n    analyses = {\n        f"R{i:02d}": payload(f"R{i:02d}", score=95-i, sector="Technology", expected=35-i * 0.2)\n        for i in range(12)\n    }\n    plan = build_optimizer_plan(\n        analyses, profile="HIGH", visible_limit=20, shortlist_limit=10,\n        target_positions=6, max_positions=7, min_rank_score=62\n    )\n    assert all(r.get("decision_reason") for r in plan["visible"])\n    rank_11 = plan["visible"][10]\n    assert rank_11["entry_signal"] in {"STRONG BUY", "BUY", "STARTER BUY"}\n    assert rank_11["optimizer_action"] == "PASS"\n    assert "Top-10 shortlist required" in rank_11["decision_reason"]\n\n\ndef test_gwre_style_policy_change_rechecks_without_buy_state_transition(monkeypatch):\n    from dataclasses import replace\n    import app.scanner as scanner_mod\n\n    radar = RadarService(provider=object(), ai=object())\n    gwre = payload("GWRE", score=77, sector="Technology", expected=25, price=100)\n\n    # GWRE becomes actionable once, then remains BUY with exactly the same state.\n    assert radar._paper_entry_event(gwre) is True\n    assert radar._paper_entry_event(dict(gwre)) is False\n\n    # Policy state is tracked independently of ticker state.\n    assert radar._paper_optimizer_invalidation_event() is True\n    assert radar._paper_optimizer_invalidation_event() is False\n\n    # Simulate a portfolio-eligibility/threshold change while GWRE stays BUY.\n    monkeypatch.setattr(\n        scanner_mod, "settings",\n        replace(scanner_mod.settings, optimizer_min_rank_score=scanner_mod.settings.optimizer_min_rank_score + 1),\n    )\n    assert radar._paper_optimizer_invalidation_event() is True\n    assert radar._paper_entry_event(dict(gwre)) is False\n\n\ndef test_scan_once_policy_invalidation_forces_full_paper_optimizer_run(monkeypatch):\n    import app.scanner as scanner_mod\n\n    radar = RadarService(provider=object(), ai=object())\n    monkeypatch.setattr(radar, "candidate_symbols", lambda: [])\n    monkeypatch.setattr(radar, "_enrich_strategic_top_candidates", lambda: (False, []))\n    monkeypatch.setattr(radar, "_sync_rotation_alerts", lambda: None)\n    calls = []\n\n    def fake_paper_cycle(provider, *, force_rebalance=False, entry_event=False):\n        calls.append(entry_event)\n        return {"status": "ok"}\n\n    monkeypatch.setattr(scanner_mod, "run_paper_cycle", fake_paper_cycle)\n\n    first = radar.scan_once(force=True)\n    assert first["paper_optimizer_invalidated"] is True\n    assert calls == [True]\n\n    calls.clear()\n    second = radar.scan_once(force=True)\n    assert second["paper_optimizer_invalidated"] is False\n    assert calls == [False]\n'''
    # The raw string above deliberately contains escaped newlines; convert them.
    addition = addition.replace("\\n", "\n")
    backup = test_path.with_suffix(test_path.suffix + ".gwre.bak")
    if not backup.exists():
        shutil.copy2(test_path, backup)
    test_path.write_text(test_text.rstrip() + addition + "\n", encoding="utf-8")
    print("PATCHED tests/test_optimizer.py")
else:
    print("SKIP tests/test_optimizer.py: regression tests already present")

print("\nGWRE optimizer revalidation patch applied successfully.")
print("Recommended verification: pytest tests/test_optimizer.py")
