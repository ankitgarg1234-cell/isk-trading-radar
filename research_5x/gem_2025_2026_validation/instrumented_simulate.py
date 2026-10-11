def simulate(cfg, frames, panel, calendar, start=START, end=END, cost_bps=20.0, exclude=()):
    cash = CAPITAL
    scheduled = {}
    suppressed = []
    raw_membership = load_gz(REPO / 'backtests/staged/wf3_prices.json.gz')
    start_members, membership_changes = membership(raw_membership)
    if int(cfg.get('delay_sessions', 0)) < 0:
        raise ValueError('Delay must be nonnegative')
    if cfg.get('inverse_vol') and cfg.get('preserve_weights'):
        raise ValueError('Weight-drift ablation is restricted to equal-entry-weight candidates')
    held = {}
    ledger = []
    curve = []
    signals = []
    pending = None
    cum_cost = 0.0
    pnl = defaultdict(float)
    basis = {}
    notional_sum = 0.0
    stale = 0
    max_participation = 0.0
    spin_sales = {}
    events = []
    monthg = {ds: g.set_index('ticker') for ds, g in panel.groupby('date')}
    membership_actions = defaultdict(list)
    raw = load_gz(REPO / 'backtests/staged/wf3_prices.json.gz')
    for e in membership(raw)[1]:
        membership_actions[e['date']].append(e)

    def mark(sym, ds, key='raw_close'):
        f = frames[sym]
        if ds in f.index:
            return float(f.loc[ds, key])
        z = f.loc[f.index < ds]
        return float(z.iloc[-1][key]) if len(z) else None

    def trade(sym, qty, ds, side):
        nonlocal cash, cum_cost, notional_sum, max_participation
        if qty <= 0 or ds not in frames[sym].index:
            return
        px = float(frames[sym].loc[ds, 'raw_open'])
        gross = qty * px
        cost = gross * cost_bps / 10000
        if side == 'BUY':
            qty = min(qty, math.floor(max(0, cash) / (px * (1 + cost_bps / 10000))))
            if qty <= 0:
                return
            gross = qty * px
            cost = gross * cost_bps / 10000
            cash -= gross + cost
            held[sym] = held.get(sym, 0) + qty
            basis[sym] = basis.get(sym, 0) + gross + cost
        else:
            qty = min(qty, held.get(sym, 0))
            gross = qty * px
            cost = gross * cost_bps / 10000
            oldqty = held[sym]
            oldbasis = basis[sym] * qty / oldqty
            cash += gross - cost
            pnl[sym] += gross - cost - oldbasis
            held[sym] -= qty
            basis[sym] -= oldbasis
            if held[sym] < 1e-09:
                held.pop(sym)
                basis.pop(sym, None)
        cum_cost += cost
        notional_sum += gross
        adv = float(frames[sym].loc[ds, 'adv20'])
        max_participation = max(max_participation, gross / adv if adv > 0 else 0)
        ledger.append({'date': ds, 'ticker': sym, 'side': side, 'shares': qty, 'nominal_open': px, 'gross': gross, 'cost': cost, 'cash_after': cash})
    for ds in [d for d in calendar if start <= d <= end]:
        for sym in list(held):
            if ds in frames[sym].index:
                r = frames[sym].loc[ds]
                if (sym, ds) in SPINOFFS:
                    child, ratio = SPINOFFS[sym, ds]
                    childqty = held[sym] * ratio
                    parentvalue = held[sym] * float(r.raw_close)
                    childvalue = childqty * mark(child, ds)
                    childbasis = basis[sym] * childvalue / (parentvalue + childvalue)
                    basis[sym] -= childbasis
                    basis[child] = basis.get(child, 0) + childbasis
                    held[child] = held.get(child, 0) + childqty
                    spin_sales[child] = ds
                    events.append({'date': ds, 'parent': sym, 'parent_shares': held[sym], 'child': child, 'child_shares': childqty, 'basis_to_child': childbasis, 'policy': 'sell next available session open; fractional entitlement approximation'})
                else:
                    held[sym] *= float(r.split)
                div = held[sym] * float(r.dividend)
                cash += div
                pnl[sym] += div
            else:
                stale += 1
        for child, eventdate in list(spin_sales.items()):
            if ds > eventdate and child in held and (ds in frames[child].index):
                trade(child, held[child], ds, 'SELL')
                spin_sales.pop(child)
        pending = scheduled.pop(ds, None)
        if pending and int(cfg.get('delay_sessions', 0)) > 0:
            active = set(start_members)
            for event in membership_changes:
                if event['date'] > ds:
                    break
                active.discard(event.get('removed'))
                if event.get('added'):
                    active.add(event['added'])
            old_targets, old_weights, is_sticky = pending
            keep = [(s, w) for s, w in zip(old_targets, old_weights) if s in active]
            suppressed.extend(({'date': ds, 'ticker': s, 'reason': 'not a member at delayed fill'} for s in old_targets if s not in active))
            pending = ([s for s, w in keep], [w for s, w in keep], is_sticky)
        if pending:
            cfg_targets, weights, sticky = pending
            pending = None
            eq_open = cash + sum((q * mark(s, ds, 'raw_open') for s, q in held.items()))
            if sticky:
                for s in list(held):
                    if s not in cfg_targets:
                        trade(s, held[s], ds, 'SELL')
                    elif held[s] * mark(s, ds, 'raw_open') > 0.25 * eq_open:
                        trade(s, max(0, held[s] - math.floor(0.25 * eq_open / mark(s, ds, 'raw_open'))), ds, 'SELL')
                empty = [s for s in cfg_targets if s not in held]
                budget = min(cash, eq_open * len(empty) * min(0.25, 1 / cfg['n']))
                for s in empty:
                    trade(s, math.floor(budget / max(1, len(empty)) / mark(s, ds, 'raw_open') / (1 + cost_bps / 10000)), ds, 'BUY')
            else:
                desired = {s: math.floor(eq_open * w / mark(s, ds, 'raw_open') / (1 + cost_bps / 10000)) for s, w in zip(cfg_targets, weights)}
                for s in list(held):
                    if held[s] > desired.get(s, 0):
                        trade(s, held[s] - desired.get(s, 0), ds, 'SELL')
                for s in cfg_targets:
                    if desired[s] > held.get(s, 0):
                        trade(s, desired[s] - held.get(s, 0), ds, 'BUY')
        removed = [e['removed'] for e in membership_actions.get(ds, []) if e.get('removed') in held]
        if removed:
            for s in removed:
                trade(s, held[s], ds, 'SELL')
        eq = cash + sum((q * mark(s, ds) for s, q in held.items()))
        if cash < -1e-05:
            raise AssertionError('Negative cash')
        curve.append({'date': ds, 'equity': eq, 'cash': cash, 'exposure': 1 - cash / eq, 'positions': len(held), 'cumulative_cost': cum_cost, 'holdings_json': json.dumps(held, sort_keys=True), 'marks_json': json.dumps({s: mark(s, ds) for s in held}, sort_keys=True)})
        if ds in monthg:
            g = monthg[ds].copy()
            g = g[~g.index.isin(exclude)]
            g = g[g[cfg['score']].notna() & (g[cfg['score']] > 0)]
            if cfg['filter'] == 'V':
                g = g[g.V]
            elif cfg['filter'] == 'VMGE':
                g = g[g.V & g.M & g.G & g.E]
            elif cfg['filter'] == 'MG':
                g = g[g.M & g.G]
            elif cfg['filter'] == 'compression':
                g = g[g.M & (g.compression < 0.7)]
            elif cfg['filter'] == 'growth_margin':
                g = g[g.G & g.E & (g.margin_delta_pp > 3)]
            if cfg.get('quarterly') and int(ds[5:7]) not in (3, 6, 9, 12):
                continue
            if cfg.get('annual') and int(ds[5:7]) != 1:
                continue
            ranked = g.sort_values([cfg['score']], ascending=False, kind='stable')
            targets = []
            if cfg.get('sticky') or cfg.get('retain_rank35'):
                ranks = {s: i + 1 for i, s in enumerate(ranked.index)}
                targets = [s for s in held if ranks.get(s, 999) <= 35]
                targets += [s for s in list(ranked.index)[:20] if s not in targets][:max(0, cfg['n'] - len(targets))]
            else:
                sectors = defaultdict(int)
                for s, r in ranked.iterrows():
                    if cfg.get('sector_cap') and sectors[r.sector] >= round(cfg['n'] * cfg['sector_cap']):
                        continue
                    targets.append(s)
                    sectors[r.sector] += 1
                    if len(targets) >= cfg['n']:
                        break
            if cfg.get('inverse_vol') and targets:
                w = np.array([1 / max(0.1, float(g.loc[s, 'vol63'])) for s in targets])
                w = w / w.sum() * min(1, len(targets) / cfg['n'])
            else:
                w = np.full(len(targets), 1 / cfg['n'])
            if cfg.get('regime'):
                f = frames['SPY']
                i = f.index.get_loc(ds)
                if i >= 199 and f.loc[ds, 'close'] < f.close.iloc[i - 199:i + 1].mean():
                    w = w * 0.25
            signals.append({'date': ds, 'tickers': '|'.join(targets), 'target_gross': float(sum(w))})
            due_index = calendar.index(ds) + 1 + int(cfg.get('delay_sessions', 0))
            due = calendar[due_index] if due_index < len(calendar) else None
            signals[-1]['scheduled_fill_date'] = due
            signals[-1]['additional_delay_sessions'] = int(cfg.get('delay_sessions', 0))
            signals[-1]['holding_rule'] = cfg.get('holding_rule', 'rebalance')
            if due is not None and due <= end:
                scheduled[due] = (targets, list(w), bool(cfg.get('sticky') or cfg.get('preserve_weights')))
    c = pd.DataFrame(curve)
    a = c.equity.to_numpy()
    dd = np.minimum(0, a / np.maximum.accumulate(np.r_[CAPITAL, a])[1:] - 1)
    annual = {}
    prev = CAPITAL
    for year, g in c.groupby(c.date.str[:4]):
        annual[year] = (g.equity.iloc[-1] / prev - 1) * 100
        prev = g.equity.iloc[-1]
    r = rolling_windows(c)
    finalpnl = dict(pnl)
    for s, q in held.items():
        finalpnl[s] = finalpnl.get(s, 0) + q * mark(s, c.date.iloc[-1]) - basis[s]
    denom = sum((v for v in finalpnl.values() if v > 0))
    top = sorted(finalpnl.items(), key=lambda x: x[1], reverse=True)
    result = {'name': cfg['name'], 'start': start, 'end': end, 'cost_bps_per_side': cost_bps, 'net_return_pct': (a[-1] / CAPITAL - 1) * 100, 'cagr_pct': ((a[-1] / CAPITAL) ** (365.25 / (date.fromisoformat(c.date.iloc[-1]) - date.fromisoformat(c.date.iloc[0])).days) - 1) * 100, 'max_dd_pct': float(dd.min() * 100), 'annual_returns_pct': annual, 'worst_complete_calendar_year_pct': min((v for k, v in annual.items() if k in ('2024', '2025'))) if start == START else None, 'rolling12_max_pct': r.return_pct.max() if len(r) else None, 'rolling12_median_pct': r.return_pct.median() if len(r) else None, 'rolling12_loss_frequency_pct': (r.return_pct < 0).mean() * 100 if len(r) else None, 'rolling12_5x_count': int((r.return_pct >= 400).sum()) if len(r) else 0, 'average_exposure_pct': c.exposure.mean() * 100, 'trade_count': len(ledger), 'traded_notional_over_initial': notional_sum / CAPITAL, 'annual_oneway_turnover_over_avg_equity': notional_sum / 2 / c.equity.mean() / ((date.fromisoformat(c.date.iloc[-1]) - date.fromisoformat(c.date.iloc[0])).days / 365.25), 'total_cost_dollars': cum_cost, 'stale_held_marks': stale, 'max_trade_adv_fraction_pct': max_participation * 100, 'top3_share_positive_pnl_pct': sum((max(v, 0) for s, v in top[:3])) / denom * 100 if denom else None, 'pnl_by_ticker': dict(top), 'corporate_distributions': events, 'accounting_residual_dollars': a[-1] - CAPITAL - sum(finalpnl.values())}
    result['suppressed_delayed_entries'] = suppressed
    return (result, c, pd.DataFrame(ledger), r, pd.DataFrame(signals))
