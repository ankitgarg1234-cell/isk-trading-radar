"""Synthetic point-in-time membership fixtures; no market-data downloads."""
import unittest

from research.spgm_universe import (
    company_counts, construct, deduplicate, eligibility, evidence_index,
    country_usable, latest_public, lei_valid, public_before, queries_for, resolve_field, ticker_at_cutoff,
)
from research.spgm_universe_report import month_ranges


def row(sid="sec", portfolio="2022-06-30", public="2022-08-26T12:00:00+00:00", **changes):
    result = {"snapshot_id": sid, "row_number": "1", "portfolio_date": portfolio,
              "publication_date": public[:10], "available_at": public,
              "name": "Synthetic Alpha", "title": "Synthetic Alpha", "asset_category": "EC",
              "balance": "10", "isin": "US0378331005", "cusip": "037833100", "sedol": "",
              "source_ticker": "", "company_lei": "", "country": "US", "currency": "USD",
              "sector": "", "sector_scheme": "", "raw_source_sha256": "synthetic",
              "mapped_ticker": "FUTURE", "ticker_mapping_available_at": "2026-10-10T12:00:00+00:00"}
    result.update(changes)
    return result


def snapshot(r):
    return {"snapshot_id": r["snapshot_id"], "portfolio_date": r["portfolio_date"],
            "available_at": r["available_at"], "source_type": "SEC NPORT-P" if r["asset_category"] != "unclassified" else "archived publisher XLSX"}


def index_for(rows, cutoff):
    groups = {}
    snapshots = {}
    for r in rows:
        groups.setdefault(r["snapshot_id"], []).append(r)
        snapshots[r["snapshot_id"]] = snapshot(r)
    return evidence_index(list(snapshots.values()), groups, cutoff)


class UniverseTests(unittest.TestCase):
    def test_publication_must_be_strictly_before_cutoff(self):
        s = snapshot(row())
        self.assertFalse(public_before(s, s["available_at"]))
        self.assertTrue(public_before(s, "2022-08-26T12:00:01+00:00"))
        with self.assertRaises(ValueError):
            public_before(s, "2022-08-26T12:00:01")

    def test_later_filing_not_used_before_publication(self):
        old = snapshot(row())
        newer = snapshot(row("new", "2022-09-30", "2022-11-28T12:00:00+00:00"))
        self.assertEqual(latest_public([old, newer], "2022-10-31T23:59:59+00:00")["snapshot_id"], "sec")
        self.assertEqual(latest_public([old, newer], "2022-11-30T23:59:59+00:00")["snapshot_id"], "new")

    def test_later_amendment_does_not_displace_newer_portfolio(self):
        newer = snapshot(row("new", "2022-09-30", "2022-11-28T12:00:00+00:00"))
        amended_old = snapshot(row("amended", "2022-06-30", "2022-12-01T12:00:00+00:00"))
        self.assertEqual(latest_public([newer, amended_old], "2022-12-31T23:59:59+00:00")["snapshot_id"], "new")

    def test_common_equity_only_positive_units_and_valid_ids(self):
        self.assertEqual(eligibility(row(), {})[0], "eligible")
        for changes in [{"asset_category": "EP"}, {"asset_category": "DE"}, {"asset_category": "STIV"},
                        {"balance": "0"}, {"balance": "-1"}, {"balance": "NaN"}, {"balance": "bad"},
                        {"cusip": "", "isin": "US0378331006"}]:
            self.assertEqual(eligibility(row(**changes), {})[0], "excluded")

    def test_workbook_type_requires_public_prior_id_evidence(self):
        book = row("book", "2022-10-04", "2022-10-07T12:00:00+00:00", asset_category="unclassified", isin="")
        future_sec = row("later", "2022-09-30", "2022-11-28T12:00:00+00:00")
        self.assertEqual(eligibility(book, index_for([book, future_sec], "2022-10-31T23:59:59+00:00"))[0], "provisional")
        self.assertEqual(eligibility(book, index_for([book, future_sec], "2022-11-30T23:59:59+00:00"))[0], "eligible")

    def test_conflicting_instrument_classes_are_not_assumed_stocks(self):
        stock = row()
        preferred = row(row_number="2", asset_category="EP")
        book = row("book", "2022-10-04", "2022-10-07T12:00:00+00:00", asset_category="unclassified")
        status, reason, _ = eligibility(book, index_for([stock, preferred, book], "2022-10-31T23:59:59+00:00"))
        self.assertEqual(status, "provisional")
        self.assertIn("conflicting", reason)

    def test_future_retrospective_ticker_never_enters_pit_record(self):
        original = row()
        cutoff = "2022-10-31T23:59:59+00:00"
        groups = {"sec": [original]}
        eligible, _, _ = construct(snapshot(original), groups, index_for([original], cutoff), cutoff)
        self.assertEqual(eligible[0]["pit_ticker"], "")
        self.assertNotIn("mapped_ticker", eligible[0])
        self.assertEqual(original["mapped_ticker"], "FUTURE")

    def test_ticker_mapping_retains_historical_source_not_later_symbol(self):
        old = row("old", "2022-06-30", "2022-08-26T12:00:00+00:00", source_ticker="OLD")
        future = row("future", "2022-09-30", "2022-11-28T12:00:00+00:00", source_ticker="NEW")
        target = row("book", "2022-10-04", "2022-10-07T12:00:00+00:00", asset_category="unclassified")
        idx = index_for([old, future, target], "2022-10-31T23:59:59+00:00")
        ticker, _, sources = ticker_at_cutoff(target, idx)
        self.assertEqual(ticker, "OLD")
        self.assertEqual(sources[0]["snapshot_id"], "old")

    def test_conflicting_source_tickers_are_ambiguous(self):
        a = row(source_ticker="ONE")
        b = row(row_number="2", source_ticker="TWO")
        ticker, status, _ = ticker_at_cutoff(a, index_for([a, b], "2022-10-31T23:59:59+00:00"))
        self.assertEqual(ticker, "")
        self.assertEqual(status, "ambiguous")

    def test_currency_and_name_do_not_fill_country_or_type(self):
        target = row("book", "2022-10-04", "2022-10-07T12:00:00+00:00", asset_category="unclassified", country="", isin="", cusip="", sedol="2046251")
        self.assertEqual(resolve_field(target, {}, "country")[0], "")
        self.assertEqual(eligibility(target, {})[0], "provisional")

    def test_unspecified_country_preserved_and_not_inferred_from_isin(self):
        original = row(country="XX")
        cutoff = "2022-10-31T23:59:59+00:00"
        eligible, _, _ = construct(snapshot(original), {"sec": [original]}, index_for([original], cutoff), cutoff)
        self.assertEqual(eligible[0]["original_country"], "XX")
        self.assertEqual(eligible[0]["country"], "")
        self.assertFalse(country_usable("XX"))

    def test_duplicate_instruments_preserve_source_positions(self):
        a = row(country_resolution="source", company_lei_resolution="missing", pit_ticker="", pit_ticker_status="missing")
        b = {**a, "row_number": "2", "balance": "5"}
        result = deduplicate([a, b])
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["source_position_count"], 2)
        self.assertIn('"row_number": "2"', result[0]["source_position_rows_json"])

    def test_company_share_lines_not_deduplicated_as_securities(self):
        lei = "549300S4KLFTLO7GSQ80"
        self.assertTrue(lei_valid(lei))
        a = row(company_lei=lei, company_lei_resolution="source", country_resolution="source", pit_ticker="", pit_ticker_status="missing")
        b = row(row_number="2", isin="US5949181045", cusip="594918104", company_lei=lei, company_lei_resolution="source", country_resolution="source", pit_ticker="", pit_ticker_status="missing")
        securities = deduplicate([a, b])
        self.assertEqual(len(securities), 2)
        self.assertEqual(company_counts(securities)["estimated_unique_company_groups"], 1)

    def test_unverified_company_count_is_labeled_estimate(self):
        a = row(company_lei_resolution="missing", instrument_key="isin:synthetic")
        result = company_counts([a])
        self.assertEqual(result["distinct_LEI_identified_issuers"], 0)
        self.assertEqual(result["estimated_unique_company_groups"], 1)
        self.assertIn("unknown", result["unique_company_count_exact"])

    def test_tsmc_not_confused_with_similarly_named_other_company(self):
        self.assertIn("TSMC", queries_for(row(name="TAIWAN SEMICONDUCTOR SP ADR")))
        self.assertNotIn("TSMC", queries_for(row(name="Taiwan Semiconductor Co Ltd")))
        self.assertIn("AMD", queries_for(row(name="ADVANCED MICRO DEVICES")))

    def test_holding_provenance_mismatch_is_rejected(self):
        r = row()
        bad = {**r, "available_at": "2023-01-01T00:00:00+00:00"}
        with self.assertRaises(ValueError):
            evidence_index([snapshot(r)], {"sec": [bad]}, "2023-02-01T00:00:00+00:00")

    def test_company_month_ranges_do_not_fill_unobserved_gaps(self):
        self.assertEqual(month_ranges(["2024-03", "2023-12", "2024-01"]), "2023-12–2024-01; 2024-03")
        self.assertEqual(month_ranges([]), "none")


if __name__ == "__main__":
    unittest.main()
