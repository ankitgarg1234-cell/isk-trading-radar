"""Observed production headlines and shared entry-policy boundary controls."""
import copy
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.analysis_engine import (news_analysis, catalyst_calculation,
    valuation_calculation, score_bundle, classify_lane, position_action)
from app.portfolio_engine import entry_attention_signal, build_optimizer_plan, system_signal
from app.scanner import _attention_buy_signal
from app.score_band_capture import compact_observation
from app.score_band_experiment import entry_check
from app.trading_rules import qualification_check, entry_status
from app.main import app
from tests.helpers import bundle
from tests.test_score_band_experiment import observation

CASES = json.loads((Path(__file__).parent/'fixtures/catalyst_valuation_cases.json').read_text())


def news(*titles):
    return news_analysis([{"title": title, "publisher": "Reuters", "published": "2026-10-05T18:00:00Z"}
                          for title in titles], symbol="MSFT", company_name="Microsoft Corp", asof="2026-10-05T18:30:00Z")


def test_observed_broker_upgrade_is_factual_despite_destination_buy_rating():
    case = CASES['MSFT']
    n = news_analysis(case['news'], symbol='MSFT', company_name=case['company'], asof=case['asof'])
    upgrade = next(x for x in n['items'] if x['title'].startswith('Melius Research upgrades'))
    assert upgrade['matched_events'] == [{'type':'rating','direction':'positive','weight':1.0}]
    assert n['score'] == 9  # Was 7.5: an asserted rating action was discarded.
    # Existing policy separates rating confirmation from business catalysts.
    assert catalyst_calculation(n)['score'] == 5


@pytest.mark.parametrize('title', [
    'Could Melius Research upgrade Microsoft stock to Buy?',
    'Melius Research might upgrade Microsoft stock to Buy',
    'Should you buy Microsoft stock after a potential upgrade?',
    'Nvidia upgraded to Buy; Microsoft shares slip',
    'Could Microsoft announce an acquisition?',
    'Microsoft insider acquires shares',
])
def test_questions_forecasts_other_companies_and_insider_purchases_are_not_catalysts(title):
    n = news(title)
    assert n['positive'] == 0
    assert catalyst_calculation(n)['score'] == 5


@pytest.mark.parametrize('title,kind', [
    ('Microsoft announces acquisition of ExampleCo','acquisition'),
    ('Microsoft announces positive phase 3 trial results','trial'),
    ('Microsoft meets primary endpoints in phase III trial','trial'),
    ('Microsoft hosts investor day','analyst day'),
])
def test_existing_catalyst_categories_are_restored_as_asserted_events(title, kind):
    n = news(title)
    assert n['catalysts'] == [kind]
    assert catalyst_calculation(n)['score'] == 8


@pytest.mark.parametrize('title', [
    'Microsoft cuts guidance',
    'Microsoft announces public offering',
    'Microsoft fails primary endpoints in phase 3 trial',
    'Microsoft reports record revenue but cuts guidance',
])
def test_negative_or_mixed_material_events_never_raise_bullish_catalyst_score(title):
    n = news(title)
    assert n['high_negative_events'] == 1
    assert n['positive_material_events'] == 0
    assert catalyst_calculation(n)['score'] == 5
    assert n['score'] < 7.5


def test_duplicate_release_counts_once_and_independent_brokers_do_not_cancel():
    n = news('Microsoft announces acquisition of ExampleCo', 'Microsoft announces acquisition of ExampleCo')
    assert n['positive_material_events'] == 1 and catalyst_calculation(n)['score'] == 8
    n = news('Microsoft upgraded by Citi', 'Microsoft downgraded by UBS')
    assert n['unique_event_count'] == 2
    assert n['positive'] == n['negative'] == 1.25


@pytest.mark.parametrize('forward', [-1, 0, float('nan'), float('inf'), 'bad'])
def test_invalid_forward_pe_cannot_mask_valid_trailing_pe(forward):
    v = valuation_calculation({'forwardPE':forward,'trailingPE':18,'revenueGrowth':.3})
    assert v['score'] == 10 and v['pe'] == 18 and v['basis'] == 'trailing TTM P/E'


@pytest.mark.parametrize('pe,base', [(19.99,8),(20,7),(29.99,7),(30,5),(44.99,5),(45,3)])
def test_valuation_bands_and_growth_bonus_are_unchanged(pe,base):
    assert valuation_calculation({'forwardPE':pe})['score'] == base
    assert valuation_calculation({'forwardPE':pe,'revenueGrowth':.26})['score'] == base + (2 if pe<45 else 0)


def test_source_valuation_cases_are_explained_without_inventing_forward_estimates():
    credo = valuation_calculation(CASES['CRDO']['fundamentals'])
    microsoft = valuation_calculation(CASES['MSFT']['fundamentals'])
    assert credo['pe'] == 76.3393 and credo['score'] == 3
    assert any('blocks' in x for x in credo['reasons'])
    assert microsoft['pe'] == 28.7325 and microsoft['score'] == 7
    assert valuation_calculation({})['score'] == 5
    assert valuation_calculation({'forwardPE':22,'trailingPE':18})['pe'] == 22


@pytest.mark.parametrize('score,analyst,target,okay', [
    (69.999,90,110,False), (70,74.999,110,False), (70,None,110,False),
    (70,75,103.999,False), (70,75,104,True), (101,90,110,False),
    (90,101,110,False), (float('nan'),90,110,False),
])
def test_dashboard_alerts_and_paper_use_identical_unrounded_gates(score,analyst,target,okay):
    a = observation(score=score,analyst=analyst,target=target,stop=90)
    # A stale rounded display ratio must not override actual target geometry.
    a['risk_reward'] = 10
    before = copy.deepcopy(a)
    assert entry_check(a)[0] == okay
    assert qualification_check(a)[0] == okay
    assert bool(build_optimizer_plan({'TEST':a})['shortlist']) == okay
    assert bool(build_optimizer_plan({'TEST':a})['selected_new']) == okay
    assert (entry_attention_signal(a) is not None) == okay
    assert (_attention_buy_signal(a)[0] is not None) == okay
    assert a == before


def test_qualified_waiting_name_is_never_a_buy_and_owned_exit_is_preserved():
    a = observation(price=105,target=115,stop=90)
    a['levels']['breakout'] = 110
    plan = build_optimizer_plan({'TEST':a})
    assert plan['shortlist'] and not plan['selected_new']
    assert entry_status(a)['qualified'] and not entry_status(a)['ready']
    a.update(deterministic_score=40,analyst_score=None,lane_qualified=False,action='EXIT')
    plan = build_optimizer_plan({'TEST':a},{'TEST'})
    assert plan['visible'][0]['optimizer_action'] == 'EXIT' and not plan['selected_new']


@pytest.mark.parametrize('action',['BUY NOW','BREAKOUT BUY','CONSIDER BUYING NOW','CONSIDER STARTER BUY','STRONG BUY','BUY','STARTER BUY'])
def test_raw_buy_language_cannot_bypass_failed_gate(action):
    a=observation(score=69.9);a['action']=action
    assert system_signal(a) == 'WATCH'
    a['action']='ADD'
    assert system_signal(a,owned=True) == 'HOLD'


def test_completed_session_breakout_is_identical_for_dashboard_and_paper():
    a = observation(price=110,target=120,stop=100)
    a['history'] = [{'date':f'2026-09-{d:02d}','close':109} for d in range(1,26)] + [{'date':'2026-10-05','close':110}]
    a['levels'].update(breakout=110.2,do_not_chase=120)
    compact = compact_observation(a)
    assert entry_check(a) == entry_check(compact) == (True,'breakout',1.0)
    assert compact['levels']['breakout'] == 109.2


def test_lane_classification_no_longer_grants_core_at_69_or_without_analyst_rr_gates():
    b = bundle()
    kwargs = dict(fs=20,fconf='high',news={'items':[]},t={'avg_dollar_volume_20':20e6},
        catalyst_score=5,total_score=69.2,expected_upside_pct=5,negative_override=None,
        analyst_confirmation=84.5,entry_rr=.43)
    assert not classify_lane(b,**kwargs)['lane_qualified']
    kwargs['total_score']=70
    assert classify_lane(b,**kwargs)['lane_qualified']
    kwargs['analyst_confirmation']=None
    assert not classify_lane(b,**kwargs)['lane_qualified']
    kwargs.update(analyst_confirmation=84.5,entry_rr=.399999)
    assert not classify_lane(b,**kwargs)['lane_qualified']


def test_analysis_page_exposes_calculation_basis_and_exact_gate_status(monkeypatch):
    from app.main import radar
    b=bundle(); b['fundamentals'].update(forwardPE=None,trailingPE=76.3393)
    d={**b,**score_bundle(b),'analyst_score':74.9,'deterministic_score':69.9,'ai_score':69.9,
       'position':None,'action':'WATCH','action_reason':'Waiting','adjustments':[],'reasons':[],'risks':[],'sensitivity':[]}
    d['entry_qualification']=entry_status(d)
    monkeypatch.setattr(radar,'analyze_symbol',lambda *args,**kw:d)
    response=TestClient(app).get('/analysis/TEST?refresh=1')
    assert response.status_code == 200
    for text in ('Catalyst calculation','Valuation calculation','trailing TTM P/E 76.34','69.9','74.9','Gate failed — watch only'):
        assert text in response.text
