"""Performance and cash-flow attribution, independent of acquisition/strategy."""
from __future__ import annotations

import math
from collections import defaultdict, deque
from datetime import date, datetime
from statistics import mean, stdev


def analyze(valuations, trades, *, initial_capital, start_date, end_date, data_kind, actions=(),dividends=()):
    if data_kind not in {"SYNTHETIC_FIXTURE","VALIDATED_HISTORICAL"}:
        raise ValueError("Explicit evidence kind required")
    rows = [r for r in valuations if start_date <= r['date'] <= end_date]
    if not rows or initial_capital <= 0:
        raise ValueError("Positive initial capital and valuation observations required")
    if rows != sorted(rows,key=lambda r:r['at']) or len({r['date'] for r in rows}) != len(rows):
        raise ValueError("Ordered distinct valuation dates required")
    navs = [initial_capital]+[r['nav'] for r in rows]
    if any(not math.isfinite(n) or n<=0 for n in navs):
        raise ValueError("NAV invalid")
    returns = [b/a-1 for a,b in zip(navs,navs[1:])]
    peak,drawdown = initial_capital,0.
    for n in navs:
        peak = max(peak,n)
        drawdown = min(drawdown,n/peak-1)
    years = ((date.fromisoformat(end_date)-date.fromisoformat(start_date)).days+1)/365.25
    vol = stdev(returns)*math.sqrt(252) if len(returns)>1 else 0.
    downside = math.sqrt(mean(min(0,r)**2 for r in returns))*math.sqrt(252)
    monthly,annual = {},{}
    for length,target in ((7,monthly),(4,annual)):
        anchor = initial_capital
        for i,r in enumerate(rows):
            key = r['date'][:length]
            if i==len(rows)-1 or rows[i+1]['date'][:length]!=key:
                target[key] = r['nav']/anchor-1
                anchor = r['nav']
    # Each event belongs to the first reference valuation after it. Stop
    # proceeds are conservatively timestamped at publication, never guessed.
    selected = [t for t in trades if start_date<=t['date']<=end_date]
    selected.sort(key=lambda t:t['at'])
    payments=sorted(dividends,key=lambda d:datetime.fromisoformat(d['at']))
    lots, realized = defaultdict(deque),[]
    notional,fees = 0.,0.
    events = [(datetime.fromisoformat(t['at']),1,t) for t in selected]
    events += [(datetime.fromisoformat(a['effective_at']),0,a) for a in actions
               if start_date <= a['effective_at'][:10] <= end_date]
    for _,kind,t in sorted(events,key=lambda e:(e[0],e[1])):
        if kind==0:
            for lot in lots[t['symbol']]:
                lot[0] *= t['ratio'];lot[1] /= t['ratio']
            continue
        q,px,fee = t['shares'],t['price_usd'],t['fee']
        notional += q*px
        fees += fee
        if t['side']=='BUY':
            lots[t['symbol']].append([q,px+fee/q,t['date']])
        else:
            left = q
            while left>1e-9 and lots[t['symbol']]:
                lot = lots[t['symbol']][0]
                part = min(left,lot[0])
                realized.append(dict(symbol=t['symbol'],quantity=part,
                    pnl=part*(px-fee/q-lot[1]),holding_days=(date.fromisoformat(t['date'])-date.fromisoformat(lot[2])).days,
                    reason=t['kind']))
                lot[0] -= part;left -= part
                if lot[0]<1e-9:lots[t['symbol']].popleft()
            if left>1e-9:
                raise ValueError("Attribution requires prior lots / corporate-action-adjusted quantities")
    stocks,sectors = defaultdict(float),defaultdict(float)
    annual_stocks,annual_sectors = defaultdict(lambda:defaultdict(float)),defaultdict(lambda:defaultdict(float))
    previous, cursor, dividend_cursor = {},0,0
    for r in rows:
        flows = defaultdict(float)
        while cursor<len(selected) and datetime.fromisoformat(selected[cursor]['at'])<=datetime.fromisoformat(r['at']):
            t = selected[cursor];cursor += 1
            flows[t['symbol']] += (1 if t['side']=='SELL' else -1)*t['shares']*t['price_usd']-t['fee']
        while dividend_cursor<len(payments) and datetime.fromisoformat(payments[dividend_cursor]['at'])<=datetime.fromisoformat(r['at']):
            d=payments[dividend_cursor];dividend_cursor+=1;flows[d['symbol']]+=d['amount_usd']
        assets=dict(r['positions'])
        for s,v in r.get('receivables',{}).items():assets[s]=assets.get(s,0.)+v
        for symbol in previous.keys() | assets.keys() | flows.keys():
            pnl = assets.get(symbol,0)-previous.get(symbol,0)+flows[symbol]
            stocks[symbol] += pnl
            sectors[r['sectors'].get(symbol,'UNRESOLVED')] += pnl
            annual_stocks[r['date'][:4]][symbol] += pnl
            annual_sectors[r['date'][:4]][r['sectors'].get(symbol,'UNRESOLVED')] += pnl
        previous = assets
    residual = rows[-1]['nav']-initial_capital-sum(stocks.values())
    if abs(residual)>max(.01,initial_capital*1e-8):
        raise ValueError("Cash-flow attribution does not reconcile; actions/dividends/opening lots need adapter")
    invested = [sum(r['positions'].values())/r['nav'] for r in rows]
    return dict(data_kind=data_kind,total_return=rows[-1]['nav']/initial_capital-1,
        cagr=(rows[-1]['nav']/initial_capital)**(1/years)-1,max_drawdown=drawdown,
        annual_volatility=vol,sharpe_zero_rf=mean(returns)*252/vol if vol else None,
        sortino_zero_rf=mean(returns)*252/downside if downside else None,
        monthly_returns=monthly,annual_returns=annual,
        realized_lot_win_rate=sum(r['pnl']>0 for r in realized)/len(realized) if realized else None,
        average_holding_days_quantity_weighted=sum(r['holding_days']*r['quantity'] for r in realized)/sum(r['quantity'] for r in realized) if realized else None,
        turnover_one_way_annualized=.5*notional/mean(r['nav'] for r in rows)/years,
        average_invested_fraction=mean(invested),average_cash_fraction=1-mean(invested),
        cash_return_assumption=0.,cash_drag_counterfactual=None,
        stop_closed_lot_pnl=sum(r['pnl'] for r in realized if r['reason']=='MODELED_STOP'),
        stop_counterfactual_impact=None,fees=fees,stock_pnl=dict(stocks),sector_pnl=dict(sectors),
        dividend_cash_paid=sum(d['amount_usd'] for d in payments),
        attribution_residual=residual,realized_lots=realized,
        annual_stock_pnl={y:dict(v) for y,v in annual_stocks.items()},
        annual_sector_pnl={y:dict(v) for y,v in annual_sectors.items()},
        spy_total_return=rows[-1]['spy_nav']/initial_capital-1 if rows[-1].get('spy_nav') else None)
