import json
from dataclasses import replace

import pytest
from fastapi.testclient import TestClient

import app.main as main
import app.paper_engine as paper
from app.db import SessionLocal, RadarCandidate, PaperAccount, PaperTrade
from app.paper_engine import PAPER_ACCOUNT
from .test_webapp import full_payload


def test_manual_trade_balances_reconcile_through_buy_add_partial_and_full_close(monkeypatch):
    config = replace(main.settings, paper_trade_cost_bps=10.0, paper_starting_cash=10000.0)
    monkeypatch.setattr(main, "settings", config)
    monkeypatch.setattr(paper, "settings", config)
    monkeypatch.setattr(main.radar.provider, "fx_rate", lambda a,b: 1.0)
    quote = {"price": 414.46}
    monkeypatch.setattr(main.radar.provider, "quick_scan", lambda symbol: quote)
    client = TestClient(main.app)
    payload = full_payload("TEST")
    payload["price"] = 414.135
    with SessionLocal() as db:
        db.add(RadarCandidate(symbol="TEST", price=payload["price"], current_json=json.dumps(payload)))
        db.commit()

    before = client.get('/api/live').json()["paper"]
    assert (before["cash"], before["invested"], before["equity"]) == (10000, 0, 10000)
    response = client.post('/api/paper/positions/TEST/add', json={"shares": 10})
    assert response.status_code == 200
    assert response.json()["shares"] == 10
    bought = client.get('/api/live').json()["paper"]
    assert (bought["cash"], bought["invested"], bought["equity"]) == (5851.26, 4141.35, 9992.61)
    assert bought["absolute_return"] == -7.39
    assert bought["equity"] == pytest.approx(bought["cash"] + bought["invested"], abs=.01)
    with SessionLocal() as db:
        assert db.query(PaperTrade).one().fees == pytest.approx(4.1446)
    page = client.get('/').text
    assert 'id="paperCash">$5851.26' in page
    assert 'id="paperInvested">$4141.35' in page
    assert 'id="paperEquity">$9992.61' in page

    def mark(price):
        quote["price"] = price
        payload["price"] = price
        with SessionLocal() as db:
            candidate = db.query(RadarCandidate).one()
            candidate.price = price
            candidate.current_json = json.dumps(payload)
            db.commit()
        main._invalidate_live_cache()

    mark(420)
    assert client.post('/api/paper/positions/TEST/close', json={"shares": 3}).status_code == 200
    partial = client.get('/api/live').json()["paper"]
    assert partial["positions"][0]["shares"] == 7
    assert (partial["cash"], partial["invested"], partial["equity"]) == (7110, 2940, 10050)
    assert client.post('/api/paper/positions/TEST/add', json={"shares": 2}).status_code == 200
    added = client.get('/api/live').json()["paper"]
    assert added["positions"][0]["shares"] == 9
    assert (added["cash"], added["invested"], added["equity"]) == (6269.16, 3780, 10049.16)
    mark(425)
    assert client.post('/api/paper/positions/TEST/close', json={}).status_code == 200
    closed = client.get('/api/live').json()["paper"]
    assert closed["positions"] == []
    assert (closed["cash"], closed["invested"], closed["equity"]) == (10090.33, 0, 10090.33)
    with SessionLocal() as db:
        account = db.query(PaperAccount).filter_by(account=PAPER_ACCOUNT).one()
        trades = db.query(PaperTrade).all()
        ledger_cash = account.starting_cash + sum(
            (t.shares * t.price if t.side == "SELL" else -t.shares * t.price) - t.fees for t in trades)
        assert account.cash == pytest.approx(ledger_cash)
