"""GEM constituent identity from Wikipedia with explicit secondary-source status.

The Wikipedia S&P 500 table gives Symbol, Security, Date added, CIK.
This is current-universe discovery, NOT a certified past-effective membership
timeline. All results are raw evidence and require issuer/SEC identity matching.
"""
from __future__ import annotations
from html.parser import HTMLParser
import re

class WikipediaMembersHold(ValueError): pass

class _Table(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.inside=False;self.row=None;self.cell=None;self.tables=[];self.rows=[]
    def handle_starttag(self,tag,attrs):
        if tag=="table":
            attrs=dict(attrs)
            self.inside = attrs.get("id")=="constituents" or ("wikitable" in attrs.get("class","") and not self.tables)
        if not self.inside:return
        if tag=="tr":self.row=[]
        if tag in ("td","th") and self.row is not None:self.cell=[]
    def handle_data(self,data):
        if self.inside and self.cell is not None:self.cell.append(data)
    def handle_endtag(self,tag):
        if not self.inside:return
        if tag in ("td","th") and self.cell is not None:
            self.row.append(" ".join("".join(self.cell).split()));self.cell=None
        if tag=="tr" and self.row is not None:
            if self.row:self.rows.append(self.row)
            self.row=None
        if tag=="table":
            self.tables.append(self.rows);self.inside=False

def parse_wikipedia_members(raw:bytes):
    if not isinstance(raw,bytes) or not 1000<len(raw)<3_000_000:
        raise WikipediaMembersHold("Invalid Wikipedia HTML length")
    page=_Table()
    page.feed(raw.decode("utf-8"))
    if not page.rows:raise WikipediaMembersHold("Constituent table absent")
    headings=[h.lower().strip() for h in page.rows[0]]
    try:
        sym=headings.index("symbol"); cik=headings.index("cik")
    except ValueError:raise WikipediaMembersHold("Symbol/CIK table columns missing") from None
    seen=set();out=[]
    for row in page.rows[1:]:
        if len(row)<=max(sym,cik):raise WikipediaMembersHold("Malformed constituent row")
        ticker=row[sym].strip().upper().replace(" ","")
        number=row[cik].strip()
        if not re.fullmatch(r"[A-Z0-9.-]{1,16}",ticker) or not re.fullmatch(r"0*[0-9]{1,10}",number):
            raise WikipediaMembersHold("Unrecognized ticker or CIK")
        if ticker in seen:raise WikipediaMembersHold("Duplicate ticker")
        seen.add(ticker)
        out.append({"ticker":ticker,"cik":number.zfill(10)})
    if not 480<=len(out)<=600:raise WikipediaMembersHold("Unexpected S&P count")
    return {"schema":"gem-current-members-secondary-v1",
            "source":"https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            "classification":"SECONDARY_CURRENT_SNAPSHOT_NOT_HISTORICAL_CERTIFICATION",
            "securities":out,"count":len(out),
            "unique_issuers":len(set(r["cik"] for r in out)),
            "qa":"CIK identity must match original SEC accession; updates require snapshots and change review"}
