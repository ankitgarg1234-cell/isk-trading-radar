"""Explicit sector admission and sensitivity; no provider calls or name guesses."""
from __future__ import annotations

import copy
from collections import Counter, defaultdict
from datetime import datetime

from research.spgm_strategy_audit import dated_verified
from research.strategy_kernel import load_kernel

STRICT_PIT = 'STRICT_PIT'
EXPLORATORY_CURRENT_GICS = 'EXPLORATORY_CURRENT_GICS'
MODES = (STRICT_PIT, EXPLORATORY_CURRENT_GICS)
SECTORS = frozenset(load_kernel()['ETFS'])


def validate_mode(mode):
    if mode not in MODES:
        raise ValueError('Unknown classification admission mode')
    return mode


def timestamp(value):
    result = datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('Sector evidence requires aware timestamps')
    return result


def evidence(record, member):
    if record.get('instrument_key') != member.get('instrument_key'):
        raise ValueError('Sector evidence security identity mismatch')
    if record.get('sector_scheme') != 'GICS' or record.get('sector') not in SECTORS:
        raise ValueError('Documented original eleven-sector GICS label required')
    if not all(record.get(k) for k in ('source_url', 'evidence_file', 'sha256',
                                      'retrieved_at', 'classification_asof', 'taxonomy_version')):
        raise ValueError('Incomplete classification provenance')
    timestamp(record['retrieved_at']); timestamp(record['classification_asof'])
    if timestamp(record['classification_asof']) > timestamp(record['retrieved_at']):
        raise ValueError('Classification snapshot dated after retrieval')
    if record.get('identity_ambiguous'):
        raise ValueError('Ambiguous classification identity')


def resolve_sector(member, at, mode=STRICT_PIT):
    """Returns a copy. Current evidence never gains historical verification."""
    validate_mode(mode)
    result = copy.deepcopy(member)
    if member.get('sector_scheme') == 'GICS' and member.get('sector') in SECTORS and dated_verified(member, 'sector', at.isoformat()):
        result['classification_audit'] = dict(mode=mode, status='HISTORICALLY_VERIFIED',
            approximate=False, sector=member['sector'], source_url=member['sector_source_url'])
        return result
    if mode == STRICT_PIT:
        raise ValueError('Historical GICS verification absent/current/future')
    current = member.get('current_gics')
    if not isinstance(current, dict):
        raise ValueError('Documented current GICS fallback absent')
    evidence(current, member)
    corrected = []
    for record in member.get('historical_gics_corrections', []):
        evidence(record, member)
        start = timestamp(record['effective_from'])
        end = timestamp(record['effective_to']) if record.get('effective_to') else None
        if end and end <= start:
            raise ValueError('Invalid historical correction interval')
        if start <= at and (end is None or at < end):
            corrected.append(record)
    if len(corrected) > 1:
        raise ValueError('Overlapping historical sector corrections')
    record = corrected[0] if corrected else current
    if corrected and not record.get('available_at'):
        raise ValueError('Historical correction knowledge date absent')
    verified = bool(corrected and record.get('verification') == 'historically_verified'
                    and timestamp(record['available_at']) < at)
    result['sector'] = record['sector']
    result['sector_scheme'] = 'GICS'
    # Keep old fields as evidence, never use them to upgrade current data.
    result['sector_verification'] = 'historically_verified' if verified else 'exploratory_approximation'
    if verified:
        result.update(sector_source_url=record['source_url'], sector_available_at=record['available_at'],
            sector_effective_from=record['effective_from'], sector_effective_to=record.get('effective_to'))
    status = 'HISTORICALLY_VERIFIED_CORRECTION' if verified else ('RETROSPECTIVE_CORRECTION' if corrected else 'CURRENT_GICS_BACKFILL')
    result['classification_audit'] = dict(mode=mode, status=status, approximate=not verified,
        sector=record['sector'], current_sector=current['sector'], original_sector=member.get('sector'),
        source=copy.deepcopy(record), current_source=copy.deepcopy(current),
        historical_truth_established=verified,
        limitation=None if verified else 'Classification uses evidence not established as observable at this historical cutoff')
    return result


def coverage(snapshots, mode):
    """Quantifies every monthly/country denominator; no unresolved row dropped."""
    validate_mode(mode)
    out = []
    for snapshot in snapshots:
        at = timestamp(snapshot['decision_at'])
        members = snapshot['members']
        counts, country, sector, problems = Counter(), defaultdict(Counter), Counter(), []
        for member in members:
            c = member.get('country') or 'UNKNOWN'
            country[c]['total'] += 1
            try:
                row = resolve_sector(member, at, mode)
                audit = row['classification_audit']
                counts['covered'] += 1
                country[c]['covered'] += 1
                counts['approximate' if audit['approximate'] else 'historically_verified'] += 1
                counts[audit['status']] += 1
                sector[row['sector']] += 1
            except (ValueError, KeyError, TypeError) as exc:
                problems.append(dict(instrument_key=member.get('instrument_key'), reason=str(exc)))
        n = len(members)
        countries_pass = all(v['covered']/v['total'] >= .95 for v in country.values() if v['total']/max(1,n) >= .01)
        out.append(dict(decision_at=at.isoformat(), securities=n, **counts,
            covered_fraction=counts['covered']/max(1,n), approximate_fraction=counts['approximate']/max(1,n),
            country={c:dict(v) for c,v in sorted(country.items())}, sector=dict(sector), unresolved=problems,
            minimum_coverage_pass=n>0 and counts['covered']/n>=.98 and countries_pass,
            static_sensitivity=dict(uncertain_security_count=counts['approximate'],
                historically_verified_count=counts['historically_verified'],
                performance_sensitivity=None, reason='Requires validated prices and decision state'),
            executable_all_members_resolved=counts['covered']==n and n>0))
    return dict(mode=mode, snapshots=out, minimum_coverage_pass=bool(out) and all(r['minimum_coverage_pass'] for r in out),
                all_members_resolved=bool(out) and all(r['executable_all_members_resolved'] for r in out))


def decision_sensitivity(engine, day, at, members, stats, marks, cap, regime, spy_r63):
    """Before orders, recompute exact rules under disclosed stress assignments.

    Joint stresses put all approximate rows into each of the eleven sectors.
    Source-provided alternatives additionally vary individual classifications.
    These are uncertainty stresses, not claimed historical GICS or probabilities.
    """
    sessions = [d for d,t in engine.reference if t<=at]
    def decision(rows, exposure):
        _,weights,selected,_ = engine.k['_calculate_targets'](engine.state,rows,stats,exposure,marks,
            sessions=sessions,spy_r63=spy_r63)
        return dict(selected=selected,weights=weights,equity_cap=exposure)
    baseline = decision(members,cap)
    approximate = [m for m in members if m.get('classification_audit',{}).get('approximate')]
    scenarios = []
    def evaluate(name,rows):
        exposure,risk = engine.k['_sector_and_cap'](rows,stats,stats,engine.history.get('SPY',[]))
        result = decision(rows,exposure)
        scenarios.append(dict(name=name, **result, regime=risk,
            selection_changed=result['selected']!=baseline['selected'],
            max_absolute_weight_change=max([abs(result['weights'].get(s,0)-baseline['weights'].get(s,0))
                for s in result['weights'].keys()|baseline['weights'].keys()] or [0.])))
    if approximate:
        for sector in sorted(SECTORS):
            evaluate('ALL_APPROXIMATE_TO_'+sector,[dict(m,sector=sector) if m in approximate else m for m in members])
        for m in approximate:
            for sector in m.get('classification_alternatives',[]):
                if sector not in SECTORS:
                    raise ValueError('Invalid classification sensitivity alternative')
                evaluate(m['instrument_key']+'_TO_'+sector,
                         [dict(row,sector=sector) if row['instrument_key']==m['instrument_key'] else row for row in members])
    return dict(day=day,at=at.isoformat(), baseline=baseline, approximate_securities=len(approximate),
        scenarios=scenarios, scenario_count=len(scenarios), sensitivity_measured=True,
        limitation='Joint extreme stresses plus documented individual alternatives; not exhaustive combinations or verified historical classifications')
