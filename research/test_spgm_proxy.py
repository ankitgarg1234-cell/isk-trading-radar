"""Synthetic fixtures only: no downloaded holdings or credentials in tests."""
import gzip
import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from research.spgm_benchmarks import parse_factsheet
from research.spgm_proxy import (
    annotate_identifiers, available_snapshot, coverage_matrix, cusip_valid,
    benchmark_comparisons, isin_valid, map_tickers, month_ends, observed_changes,
    parse_archive, parse_exhibit, parse_nport,
    quality_fields, sedol_valid,
)
from research.spgm_sources import PublicCache, RestrictedRedirect, allowed_url, parse_index


def nport(series="S000036082", report="2022-09-30"):
    return f'''<edgarSubmission xmlns="http://www.sec.gov/edgar/nport"><formData>
    <genInfo><seriesId>{series}</seriesId><seriesName>Synthetic test fund</seriesName>
    <repPdEnd>2023-09-30</repPdEnd><repPdDate>{report}</repPdDate></genInfo>
    <invstOrSecs><invstOrSec><name>Synthetic Alpha</name><title>Class A</title>
    <lei>N/A</lei><cusip>037833100</cusip><identifiers><isin value="US0378331005"/></identifiers>
    <assetCat>EC</assetCat><invCountry>US</invCountry><currencyConditional curCd="USD"/>
    <balance>1</balance><valUSD>10</valUSD><pctVal>1</pctVal></invstOrSec></invstOrSecs>
    </formData></edgarSubmission>'''.encode()


def metadata():
    return {"accession": "synthetic-1", "index_portfolio_date": "2022-09-30",
            "accepted_eastern": "2022-11-28 12:00:00", "filing_date": "2022-11-28",
            "form_type": "NPORT-P", "xml_url": "https://www.sec.gov/synthetic.xml",
            "index_url": "https://www.sec.gov/synthetic-index.htm"}


def workbook(portfolio="04-Apr-2024"):
    # Test spreadsheet is generated in memory; identifiers are structural fixtures.
    rows = [["Fund Name:", "SPDR Portfolio MSCI Global Stock Market ETF"],
            ["Ticker Symbol:", "SPGM"], ["Holdings:", "As of " + portfolio],
            ["Name", "Ticker", "Identifier", "SEDOL", "Weight", "Sector", "Shares Held", "Local Currency"],
            ["Synthetic Alpha", "SNT", "037833100", "2046251", "1", "-", "1", "USD"]]
    from xml.sax.saxutils import escape
    content = []
    for number, values in enumerate(rows, 1):
        cells = ''.join(f'<c r="{chr(65+i)}{number}" t="inlineStr"><is><t>{escape(v)}</t></is></c>' for i, v in enumerate(values))
        content.append(f'<row r="{number}">{cells}</row>')
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as z:
        z.writestr("xl/workbook.xml", '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Holdings" sheetId="1" r:id="r1"/></sheets></workbook>')
        z.writestr("xl/_rels/workbook.xml.rels", '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
        z.writestr("xl/worksheets/sheet1.xml", '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' + ''.join(content) + '</sheetData></worksheet>')
    return stream.getvalue()


def snapshot(sid, portfolio, public):
    row = {"snapshot_id": sid, "portfolio_date": portfolio, "available_at": public}
    row.update({field: 0 for field in quality_fields()})
    return row


class SPGMTests(unittest.TestCase):
    def test_security_identifiers_validate_without_losing_leading_zeroes(self):
        self.assertTrue(isin_valid("US0378331005"))
        self.assertTrue(cusip_valid("037833100"))
        self.assertTrue(sedol_valid("2046251"))
        self.assertFalse(isin_valid("US0378331006"))
        self.assertFalse(cusip_valid("037833101"))
        self.assertFalse(sedol_valid("2046252"))

    def test_portfolio_date_not_fiscal_year_end_and_publication_retained(self):
        s, rows = parse_nport(nport(), metadata())
        self.assertEqual(s["portfolio_date"], "2022-09-30")
        self.assertEqual(s["fiscal_year_end"], "2023-09-30")
        self.assertEqual(s["available_at"], "2022-11-28T17:00:00+00:00")
        self.assertEqual(rows[0]["cusip"], "037833100")
        self.assertEqual(rows[0]["country"], "US")
        self.assertEqual(rows[0]["currency"], "USD")
        self.assertEqual(rows[0]["sector"], "")
        self.assertEqual(rows[0]["source_ticker"], "")

    def test_series_date_and_xml_entities_rejected(self):
        for data in [nport("S000000000"), nport(report="2022-08-31"), b'<!DOCTYPE doc><doc/>']:
            with self.assertRaises(ValueError):
                parse_nport(data, metadata())

    def test_later_filing_date_uses_conservative_eastern_day_bound(self):
        m = metadata()
        m["accepted_eastern"] = "2022-11-25 17:30:00"
        s, _ = parse_nport(nport(), m)
        self.assertEqual(s["public_timestamp_utc"], "2022-11-25T22:30:00+00:00")
        self.assertEqual(s["available_at"], "2022-11-29T04:59:59+00:00")

    def test_archive_date_not_publication_and_gzip_supported(self):
        s, rows = parse_archive(gzip.compress(workbook()), {"capture": "20240407120155", "url": "https://web.archive.org/synthetic"})
        self.assertEqual(s["portfolio_date"], "2024-04-04")
        self.assertEqual(s["publication_date"], "")
        self.assertEqual(s["available_at"], "2024-04-07T12:01:55+00:00")
        self.assertEqual(rows[0]["country"], "")  # USD must not become country US.
        self.assertEqual(rows[0]["sector"], "")

    def test_archive_cannot_contain_future_portfolio(self):
        with self.assertRaises(ValueError):
            parse_archive(workbook("08-Apr-2024"), {"capture": "20240407120155", "url": "https://web.archive.org/synthetic"})

    def test_no_publication_lookahead_and_amendment_versioning(self):
        original = snapshot("original", "2022-09-30", "2022-11-28T17:00:00+00:00")
        amendment = snapshot("amendment", "2022-09-30", "2022-12-10T17:00:00+00:00")
        self.assertIsNone(available_snapshot([original, amendment], "2022-10-31T23:59:59+00:00"))
        self.assertEqual(available_snapshot([original, amendment], "2022-11-30T23:59:59+00:00")["snapshot_id"], "original")
        self.assertEqual(available_snapshot([original, amendment], "2022-12-31T23:59:59+00:00")["snapshot_id"], "amendment")
        with self.assertRaises(ValueError):
            available_snapshot([original], "2022-11-30T23:59:59")

    def test_monthly_matrix_distinguishes_observation_and_lagged_availability(self):
        s = snapshot("s", "2022-12-31", "2023-02-28T17:00:00+00:00")
        rows = coverage_matrix([s])
        december, february = rows[2], rows[4]
        self.assertTrue(december["month_end_observation_exists"])
        self.assertFalse(december["month_end_observation_public_by_selection"])
        self.assertFalse(december["selected_snapshot_id"])
        self.assertEqual(february["staleness_calendar_days"], 59)
        self.assertEqual(len(month_ends()), 48)
        self.assertEqual(month_ends()[-1].isoformat(), "2026-09-30")

    def test_future_ticker_crosswalk_is_identity_only(self):
        _, old = parse_nport(nport(), metadata())
        _, future = parse_archive(workbook(), {"capture": "20240407120155", "url": "https://web.archive.org/synthetic"})
        rows = old + future
        map_tickers(rows)
        self.assertEqual(rows[0]["mapped_ticker"], "SNT")
        self.assertEqual(rows[0]["ticker_mapping_status"], "future_archive_identity_only")
        self.assertEqual(rows[0]["ticker_mapping_available_at"], "2024-04-07T12:01:55+00:00")

    def test_invalid_id_does_not_create_ticker_join(self):
        _, old = parse_nport(nport(), metadata())
        _, future = parse_archive(workbook(), {"capture": "20240407120155", "url": "https://web.archive.org/synthetic"})
        old[0].update({"isin": "US0378331006", "cusip": "037833101"})
        annotate_identifiers(old[0])
        map_tickers(old + future)
        self.assertEqual(old[0]["ticker_mapping_status"], "unmapped")

    def test_conflicting_exact_id_tickers_are_ambiguous(self):
        _, old = parse_nport(nport(), metadata())
        _, future = parse_archive(workbook(), {"capture": "20240407120155", "url": "https://web.archive.org/synthetic"})
        conflicting = {**future[0], "source_ticker": "DIFFERENT", "row_number": 2}
        map_tickers(old + future + [conflicting])
        self.assertEqual(old[0]["ticker_mapping_status"], "ambiguous_exact_identifier")
        self.assertEqual(old[0]["mapped_ticker"], "")

    def test_multifund_exhibit_scoping_and_aggregate_only_sectors(self):
        d = b'''<A href="#spgm">SPDR Portfolio MSCI Global Stock Market ETF</A>
        <A href="#other">Other ETF</A><A name="spgm"></A>
        SCHEDULE OF INVESTMENTS December 31, 2022
        Sector Breakdown as of December 31, 2022 Information Technology 19.1% TOTAL 100.0%
        <A name="other"></A>Sector Breakdown as of December 31, 2022 Financials 90.0% TOTAL 100.0%'''
        a, sectors = parse_exhibit(d, {"portfolio_date": "2022-12-31", "publication_date": "2023-02-28",
                                    "available_at": "2023-02-28T17:00:00+00:00", "snapshot_id": "s",
                                    "exhibit_url": "https://www.sec.gov/synthetic.htm"})
        self.assertEqual([s["sector"] for s in sectors], ["Information Technology"])
        self.assertFalse(a["security_level_gics_mapping_supplied"])

    def test_index_document_link_and_accepted_date(self):
        data = b'''Accepted</div><div>2023-02-28 12:00:00</div>
        Period of Report</div><div>2022-12-31</div>
        <a href="/xslFormNPORT/primary_doc.xml">styled</a>
        <a href="/primary_doc.xml">raw</a>'''
        self.assertEqual(parse_index(data, "https://www.sec.gov/index.htm")["xml_url"], "https://www.sec.gov/primary_doc.xml")

    def test_network_cannot_contact_eodhd_or_follow_disallowed_redirect(self):
        for u in ["https://eodhd.com/api/user", "http://www.sec.gov/", "https://user:password@www.sec.gov/"]:
            with self.assertRaises(ValueError):
                allowed_url(u)
        with self.assertRaises(ValueError):
            RestrictedRedirect().redirect_request(None, None, 302, "", {}, "https://eodhd.com/")

    def test_output_cannot_escape_ignored_data_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(ValueError):
                PublicCache(Path(directory))

    def test_factsheet_count_is_dated_not_membership(self):
        parsed = parse_factsheet("MSCI ACWI IMI Index With 8,036 constituents FUNDAMENTALS (SEP 30, 2026)")
        self.assertEqual(parsed, {"portfolio_date": "2026-09-30", "constituent_count": 8036})
        with self.assertRaises(ValueError):
            parse_factsheet("MSCI ACWI Index With 8,036 constituents")

    def test_count_comparison_is_not_missing_member_identity(self):
        s = snapshot("s", "2026-03-31", "2026-05-28T17:00:00+00:00")
        s["holdings_count"] = 3
        b = {"portfolio_date": "2026-03-31", "available_at": "2026-05-03T12:00:00+00:00", "constituent_count": 10}
        comparison = benchmark_comparisons([s], [b])[0]
        self.assertEqual(comparison["count_gap_not_known_missing_members"], 7)
        self.assertEqual(comparison["count_ratio_pct_not_overlap"], 30)
        self.assertEqual(comparison["missing_security_identities"], "unknown_without_full_index_membership")

    def test_last_trading_day_benchmark_retains_actual_date(self):
        b = {"portfolio_date": "2024-11-29", "available_at": "2024-12-04T17:00:00+00:00", "constituent_count": 10}
        row = next(x for x in coverage_matrix([], [b]) if x["selection_month"] == "2024-11")
        self.assertEqual(row["benchmark_count_date"], "2024-11-29")
        self.assertFalse(row["benchmark_count_public_at_selection"])

    def test_etf_observation_exit_is_not_a_delisting_or_msci_event(self):
        first = {**snapshot("old", "2022-09-30", "2022-11-28T17:00:00+00:00"), "source_type": "SEC NPORT-P"}
        second = {**snapshot("new", "2022-12-31", "2023-02-28T17:00:00+00:00"), "source_type": "SEC NPORT-P"}
        rows = observed_changes([first, second], {"old": [{"instrument_key": "synthetic:OLD", "name": "Old company"}],
                                                  "new": [{"instrument_key": "synthetic:NEW", "name": "New company"}]})
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(not x["is_msci_event"] and not x["is_confirmed_delisting"] for x in rows))


if __name__ == "__main__":
    unittest.main()
