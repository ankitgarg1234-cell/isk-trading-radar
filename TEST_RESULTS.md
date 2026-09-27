# ISK Trading Radar V1 — Test Results

**Build:** V1 Full Functional Prototype  
**Test run:** 2026-09-27  
**Result:** **25 passed / 0 failed**  
**Overall Python coverage:** **73%**

## Functional regression coverage

| Requirement | Status | Regression coverage |
|---|---|---|
| Accepted dashboard shell remains usable | PASS | Dashboard route/render test |
| Analyze any manually entered symbol | PASS | Request queue/redirect/API tests |
| Manual current-position entry | PASS | Persistence test |
| Screenshot position import | PASS | Server-AI path mocked + free browser-OCR fallback path |
| User confirmation before screenshot positions are saved | PASS | Import-confirm persistence test |
| Trade ledger | PASS | Manual BUY/SELL persistence + invalid-side rejection |
| Cash + strategic reserve | PASS | Persistence test |
| Continuous cross-sector scanner architecture | PASS | Scanner session gate + cross-sector discovery pipeline structure |
| Existing positions prioritized by scanner | PASS | Scanner ordering test |
| Explosive Runner requires strong fundamentals | PASS | Explicit fundamental-gate regression test |
| Material negative news can override high score | PASS | Override/cap regression test |
| New-position BUY NOW logic | PASS | Buy-zone decision test |
| New-position WAIT MORE logic | PASS | Deteriorating setup test |
| Existing profitable position can trigger TAKE PARTIAL PROFIT | PASS | Position-aware decision test |
| Portfolio cash deployment proposal | PASS | Optimizer test |
| Portfolio rotation proposal | PASS | Optimizer test |
| Buy / Better Buy / Breakout / Do-Not-Chase / Stop / Target levels | PASS | Analysis page + engine decision tests |
| Deterministic vs Analyst vs AI score display | PASS | Analysis-page regression test |
| Analyst vs AI expected yield / holding period | PASS | Analysis-page regression test |
| Explainable AI adjustments | PASS | AI fallback explainability test |
| “What changes the score” sensitivity | PASS | AI fallback sensitivity test |
| News sentiment/materiality/credibility/priced-in heuristic | PASS | Engine + analysis-page tests |
| Live alert API | PASS | Candidate/alert API test |
| Alert deduplication on unchanged action | PASS | Scanner persistence test |
| Health endpoint | PASS | Endpoint test |
| Unsupported screenshot file rejection | PASS | Validation test |

## Coverage summary

```text
app/analysis_engine.py   84%
app/db.py                98%
app/main.py              78%
app/scanner.py           62%
app/config.py           100%
TOTAL                    73%
```

`market.py` and the OpenAI-backed branch of `ai_engine.py` intentionally have lower local coverage because the automated suite does **not** make live network calls or spend API credits. Their interfaces are exercised through fakes/mocks so the deterministic and application layers can be tested repeatably.

## External/live items not claimed as locally verified

1. Yahoo's no-key endpoints can change, throttle, delay or return incomplete data. V1 labels this feed as a prototype source.
2. Server-side screenshot AI extraction requires `OPENAI_API_KEY`. When absent, the dashboard falls back to free Tesseract browser OCR and always asks for user confirmation.
3. Render Free can sleep after inactivity, so continuous scanning is only continuous while the service is awake. This is an infrastructure limit, not an application-logic limit.
4. The V1 market-session gate covers regular Mon-Fri 09:30–16:00 New York time. A production exchange-calendar integration is still needed for US market holidays and early closes.
5. IBKR synchronization/order execution is intentionally not included in V1. There is no automatic brokerage execution path in this build.
6. The V1 free discovery feed is cross-sector and broad, but it is not an exchange-grade exhaustive real-time scan of every US-listed equity on every tick. The scanner/provider interface is designed to accept a production feed later.

## Test command

```bash
pip install -r requirements-dev.txt
pytest --cov=app --cov-report=term --cov-report=xml:coverage.xml --junitxml=test-results.xml -q
```

Expected result for this release:

```text
25 passed
TOTAL coverage: 73%
```
