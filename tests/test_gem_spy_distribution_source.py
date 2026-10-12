"""State Street SPY original distribution-schedule evidence (not price returns)."""
from io import BytesIO

import httpx
import pytest
from reportlab.pdfgen.canvas import Canvas

from gem_data.gem_public_ingest import (
    SPY_DISTRIBUTION_SCHEDULE, fetch_one, InvalidEvidence,
)


def _pdf(text):
    output = BytesIO()
    canvas = Canvas(output, pagesize=(612, 792))
    canvas.drawString(45, 700, text)
    canvas.showPage()
    canvas.save()
    return output.getvalue()


def test_bounded_official_spy_pdf_is_only_provisional_dates_evidence():
    original = _pdf("Calendar Year 2026 Dividend Distribution Schedule State Street SPDR S&P 500 ETF Trust (SPY)")
    def respond(req):
        assert str(req.url) == SPY_DISTRIBUTION_SCHEDULE
        return httpx.Response(200, content=original,
                              headers={"content-type": "application/pdf"})
    with httpx.Client(transport=httpx.MockTransport(respond)) as client:
        raw, metrics = fetch_one(client, "benchmark")
    assert raw == original
    assert metrics["published_year"] == 2026
    assert metrics["distribution_amounts_verified"] is False
    assert metrics["spy_total_return_certified"] is False


def test_html_disguised_as_pdf_is_rejected():
    with httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, content=b"<html>fake</html>",
                                   headers={"content-type": "application/pdf"})
    )) as client:
        with pytest.raises(InvalidEvidence, match="not PDF"):
            fetch_one(client, "benchmark")


def test_pdf_not_containing_spy_identity_is_rejected():
    raw = _pdf("Unrelated investment fund Calendar Year 2026 Dividend Distribution Schedule")
    with httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(200, content=raw,
                                   headers={"content-type": "application/pdf"})
    )) as client:
        with pytest.raises(InvalidEvidence, match="identity absent"):
            fetch_one(client, "benchmark")
