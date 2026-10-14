"""No-network, no-broker regression for Yahoo alternate-source momentum triage."""
from datetime import date
from io import StringIO
import csv

from gem_data.gem_nyse_2026_manifest import published_schedule_2026
from gem_data.gem_public_universe_price_probe import (
    parse_membership,classify_yahoo_security,probe_universe)


def manifest():
    stream=StringIO()
    writer=csv.DictWriter(stream,fieldnames=["Symbol","CIK"])
    writer.writeheader()
    for i in range(503):
        writer.writerow({"Symbol":f"X{i:03d}","CIK":str(100000+i%500)})
    return stream.getvalue().encode()


class DateIndex:
    def __init__(self,day): self.day=day
    def strftime(self,fmt): return self.day


class FakeBars:
    empty=False
    def __init__(self, *, positive=True, incomplete=False):
        d=[x["session"] for x in published_schedule_2026()["sessions"]
           if "2026-03-01"<=x["session"]<="2026-09-30"][-127:]
        self.bars=[
            (DateIndex(day),{
                "Open":100.0,"High":105.0,"Low":95.0,"Close":100.0,
                "Adj Close":100+(i/126*20 if positive else -i/126*10),
                "Volume":1_000_000
            }) for i,day in enumerate(d)]
        if incomplete: self.bars.pop(5)
    def iterrows(self):return iter(self.bars)


def test_503_symbols_and_500_ciks_parser():
    symbols=parse_membership(manifest())
    assert len(symbols)==503
    assert len(set(symbols.values()))==500


def test_price_gate_uses_63_intervals_and_complete_calendar():
    sessions=[x["session"] for x in published_schedule_2026()["sessions"]
              if x["session"]<="2026-09-30"]
    pos=classify_yahoo_security("X000",FakeBars(),
                                signal_day="2026-09-30",required_sessions=sessions)
    assert pos["status"]=="OBSERVED_UNCERTIFIED"
    assert pos["r63"]>0
    assert pos["adv20"]==100_000_000
    assert pos["eligible_price_liquidity_provisional"]
    assert not pos["certified"]
    neg=classify_yahoo_security("X000",FakeBars(positive=False),
                                signal_day="2026-09-30",required_sessions=sessions)
    assert neg["r63"]<0
    assert not neg["eligible_price_liquidity_provisional"]
    missing=classify_yahoo_security("X000",FakeBars(incomplete=True),
                                signal_day="2026-09-30",required_sessions=sessions)
    assert missing["status"]=="UNRESOLVED_PRICE_QA"
    assert not missing["certified"]


def test_public_probe_preserves_502_unobserved_competitors_and_never_ranks_trades():
    class Frame(FakeBars):
        columns=type("Columns",(),{"nlevels":1})()
    report=probe_universe(
        max_symbols=1,batch_size=1,raw_fetch=lambda _:manifest(),
        quote_fetch=lambda _:Frame())
    assert report["current_membership_count"]==503
    assert report["current_issuer_count"]==500
    assert report["symbols_attempted"]==1
    assert report["full_history_observed"]==1
    assert report["positive_momentum_observed_not_certified"]==1
    assert report["final_ranking_authorized"] is False
    assert report["trading_authorized"] is False
    assert report["source_certified"] is False


def test_corporate_actions_preserved_as_unverified_ex_date_events():
    sessions=[x["session"] for x in published_schedule_2026()["sessions"]
              if x["session"]<="2026-09-30"]
    class Source(FakeBars):
        columns=["Dividends","Stock Splits"]
        def iterrows(self):
            for stamp,row in self.bars:
                d=stamp.strftime("%Y-%m-%d")
                yield stamp,{**row,"Dividends":1.25 if d=="2026-09-30" else 0.0,
                             "Stock Splits":0.0}
    row=classify_yahoo_security("X000",Source(),signal_day="2026-09-30",
                                required_sessions=sessions)
    assert row["status"]=="OBSERVED_UNCERTIFIED"
    assert row["action_fields_observed"] is True
    assert row["action_events_uncertified"]==[
        {"session":"2026-09-30","type":"DIVIDEND","value":1.25}]
    assert row["certified"] is False
