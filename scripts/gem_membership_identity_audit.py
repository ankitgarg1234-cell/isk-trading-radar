"""Evidence-linked, *research-only* effective-dated ticker identity audit.

These issuer/SEC announcements verify ticker use, not S&P membership.
Never map a new merger successor back to its predecessor's historical OHLCV,
nor mark any input as independently certified. This module is intentionally
separate from the frozen GEMv1 trading and ranking code.
"""
from __future__ import annotations
from datetime import date

# new symbol, legacy symbol, date of new symbol, CIK, dated issuer/SEC evidence
TICKER_CHANGES = (
    ("ELV", "ANTM", "2022-06-28", "0001156039", "https://www.sec.gov/Archives/edgar/data/1156039/000115603923000007/elv-20221231.htm"),
    ("BALL", "BLL", "2022-05-10", "0000009389", "https://www.sec.gov/Archives/edgar/data/9389/000000938922000010/bll-20220427x8k.htm"),
    ("META", "FB", "2022-06-09", "0001326801", "https://www.sec.gov/Archives/edgar/data/1326801/000132680122000070/may312022-exhibit991.htm"),
    ("GEN", "NLOK", "2022-11-08", "0000849399", "https://www.sec.gov/Archives/edgar/data/849399/000110465922115277/tm2229813d1_ex99-01.htm"),
    ("PARA", "VIAC", "2022-02-17", "0000813828", "https://www.sec.gov/Archives/edgar/data/813828/000081382822000011/viac-20220216.htm"),
    ("COR", "ABC", "2023-08-30", "0001140859", "https://www.sec.gov/Archives/edgar/data/1140859/000110465923096698/tm2324358d1_8k.htm"),
    ("BNY", "BK", "2026-05-21", "0001390777", "https://www.bny.com/corporate/global/en/about-us/newsroom/press-release/bny-announces-planned-change-of-stock-ticker-symbol-to-bny-130465.html"),
    ("DAY", "CDAY", "2024-02-01", "0001725057", "https://investors.dayforce.com/news-and-events/press-releases/press-release-details/2024/Ceridian-to-change-ticker-symbol-to-DAY-on-NYSE-and-TSX-effective-February-1/default.aspx"),
    ("CPAY", "FLT", "2024-03-25", "0001175454", "https://www.sec.gov/Archives/edgar/data/1175454/000162828024010593/flt-20240307.htm"),
    ("DOC", "PEAK", "2024-03-04", "0000765880", "https://www.sec.gov/Archives/edgar/data/765880/000110465924029661/tm247564d1_8k.htm"),
    ("EG", "RE", "2023-07-10", "0001095073", "https://investors.everestglobal.com/news/news-details/2023/Everest-to-Rebrand-Company-Name-and-NYSE-Ticker-to-Reflect-its-Evolution-Global-Growth-and-Diversification-Strategy/default.aspx"),
    ("FI", "FISV", "2023-06-07", "0000798354", "https://investors.fiserv.com/news-releases/news-release-details/fiserv-completes-listing-transfer-new-york-stock-exchange"),
    ("MRSH", "MMC", "2026-01-14", "0000062709", "https://www.marsh.com/en/corp/about/news/marsh-mclennan-to-change-nyse-symbol-to-mrsh.html"),
    ("RVTY", "PKI", "2023-05-16", "0000031791", "https://www.sec.gov/Archives/edgar/data/31791/000003179123000011/pki-20230702.htm"),
)

# Merger-created or successor securities require a distinct security/price
# history; a matching CIK or issuer name is NOT permission to backfill.
FIRST_LISTINGS = (
    ("VMRK", "2026-08-18", "0000906107", "https://investors.vivmarkresidential.com/news-events/press-releases/detail/113/vivmark-residential-launches-as-one-of-the-countrys-leading-real-estate-companies"),
    ("PSKY", "2025-08-07", "0002041610", "https://m.nasdaqtrader.com/TraderNews.aspx?id=ECA2025-414"),
    ("SKYD", "2026-10-07", "0002041610", "https://www.investopedia.com/market-update-skydance-shares-slide-after-merger-with-warner-bros-discovery-12161228"),
    ("SW", "2024-07-08", "0002005951", "https://www.sec.gov/Archives/edgar/data/2005951/000110465924078355/tm2418700d1_ex99-2.htm"),
)

# SAME CIK is not universally the same listed security. Preserve three
# separately traded common share classes found in the historical source.
INDEPENDENT_CLASSES = {
    ("0001652044", frozenset({"GOOG", "GOOGL"})),
    ("0001754301", frozenset({"FOX", "FOXA"})),
    ("0001564708", frozenset({"NWS", "NWSA"})),
}


def identity_issues(ticker: str, cik: str, day: date) -> list[dict]:
    issues = []
    for new, old, starts, recorded_cik, evidence in TICKER_CHANGES:
        effective = date.fromisoformat(starts)
        if cik != recorded_cik:
            continue
        if ticker == new and day < effective:
            issues.append({"code": "NEW_TICKER_NOT_YET_EFFECTIVE", "historically_used": old,
                           "effective_on": starts, "evidence": evidence})
        if ticker == old and day >= effective:
            issues.append({"code": "RETIRED_TICKER_AFTER_CHANGE", "historically_used": new,
                           "effective_on": starts, "evidence": evidence})
    for symbol, starts, recorded_cik, evidence in FIRST_LISTINGS:
        if ticker == symbol and (cik == recorded_cik or not cik) and day < date.fromisoformat(starts):
            issues.append({"code": "SECURITY_NOT_YET_LISTED", "effective_on": starts,
                           "evidence": evidence, "do_not_backfill_predecessor": True})
    return issues


def identity_screen(members: list[dict], day: date) -> dict:
    """Filter only *documentably impossible ticker eras*; never silently repair.

    Retain every rejected row and competing same-CIK class in the manifest so
    the research rank remains on HOLD until the dated source gaps are reviewed.
    """
    quarantined, accepted = [], []
    for row in members:
        problems = identity_issues(row["ticker"], row["cik"], day)
        if problems:
            quarantined.append({"ticker": row["ticker"], "cik": row["cik"],
                                "flags": problems})
        else:
            accepted.append(row)
    cik_groups: dict[str, list[str]] = {}
    for row in accepted:
        cik_groups.setdefault(row["cik"], []).append(row["ticker"])
    confirmed_classes = []
    unresolved_cik_collisions = []
    for cik, names in sorted(cik_groups.items()):
        if len(names) <= 1:
            continue
        if (cik, frozenset(names)) in INDEPENDENT_CLASSES:
            confirmed_classes.append({"cik": cik, "tickers": sorted(names)})
        else:
            unresolved_cik_collisions.append({"cik": cik, "tickers": sorted(names)})
    return {
        "raw_count": len(members), "post_symbol_era_count": len(accepted),
        "quarantined": quarantined,
        "confirmed_separate_share_classes": confirmed_classes,
        "unresolved_same_cik_collisions": unresolved_cik_collisions,
        "retained": sorted(row["ticker"] for row in accepted),
        "classification": "RESEARCH_IDENTITY_SCREEN_NOT_MEMBERSHIP_CERTIFICATION",
        "rank_authorized": False,
    }


def screen_reference_symbols(symbols: set[str], day: date) -> dict:
    """No CIK in this source: only flag unmistakably future FIRST_LISTINGS."""
    invalid, valid = [], []
    for ticker in sorted(symbols):
        checks = identity_issues(ticker, "", day)
        if checks:
            invalid.append({"ticker": ticker, "flags": checks})
        else:
            valid.append(ticker)
    return {"retained": valid, "quarantined": invalid}
