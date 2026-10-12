# GEM V1 source readiness, data requirements and independent ranking gate
**2026-10-12. Prepared for review. Does not authorize paper execution.**

## The problem revealed by the screenshot

The six UNKNOWN statuses reflected **no production-ready verified source receipts**, not an absence of every basic adapter. Current Dual Momentum code already queries a public secondary index list, Yahoo price bars, SEC companyfacts and the NYSE calendar. Separately, the user-selected read-only IBKR connector returned 250 daily OHLCV bars through 2026-10-09 for SPY, P, HPE and PSX in a bounded diagnostic probe on October 12. A chat-connected market data tool is **not** a background Render gateway or a credential that the deployed application may inherit.

**Never upgrade a source to VERIFIED just because its URL responded.** This PR now presents dated PARTIAL/STALE source evidence and the exact blockers. No GEM trades, scheduled execution or sources are approved.

## Source-of-truth contracts for the next GEM signal

| Input | Preferred collecting agent/source | Readiness condition, otherwise HOLD |
| --- | --- | --- |
| Effective-dated eligible S&P securities | Entitled official S&P DJI constituent delivery, dated change announcements, stable CIK/share-class/security identifiers; secondary GitHub member tables for *cross-check only* | Reconcile all memberships and removal/effective timing as of *signal session*, no current-membership survivorship, no unknown issuer aliases. License/access to a primary complete daily snapshot is outstanding. |
| Daily OHLCV / r63 / ADV20 | IBKR historical market-data connection **on the selected named link**, through a *separate deployed read-only gateway* using approved entitlements. Original archived Yahoo semantics retained only as a comparison fixture. | Every member gets at least 127 completed bars including the signal session, no duplicates or post-cutoff observations, r63 independently recalculated from frozen adjusted-close semantics, last 20 vendor close × volume ADV >= $10m, nominal close >= $5, next-open observation only *after* signal. Resolve symbol/contract aliases; 4 sampled contracts are not 500. |
| Original SEC 10-Q facts | SEC submissions/companyfacts for accession discovery; original filing header/index/XBRL and context for six current/prior revenue, income and operating-income uses; independent SEC specialist | Facts are public before prior-day financial cutoff, correct 60–125-day quarter / accepted amendment, same filing/context/units/CIK, current-versus-310–420-day comparator, 210-day freshness where frozen strategy requires. Missing/ambiguous competitors block selection even if chosen five were certified. SEC requires fair-access user agent and rate-limit policy. |
| Corporate actions / dividends | IBKR event metadata + issuer/SEC 8-K/original distribution notices + qualified action provider | Corporate event ledger covers every member as-of cutoff, split/dividend units and payment/ex dates separately, mergers/spinoffs/delisting cash and price adjustments reconciled; incomplete events are an explicit HOLD. |
| Session dates | Official NYSE trading hours and emergency notices; independent `pandas_market_calendars` calculation | Current dated official calendar/status reconciles month-end close, early closes, DST and true next session open; old/stale holiday page cannot prove emergency market status. |
| SPY benchmark total return | IBKR SPY market history, vetted event distributions and independent accounting | Complete aligned session-price+distribution record, same inception, whole-share cash/fee timing, independently reconciled total return—not mere SPY close-to-close. |

Sources:
- [S&P DJI indices data licensing](https://www.spglobal.com/spdji/en/about-us/data-index-licensing/)
- [SEC EDGAR APIs and originals](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [NYSE official hours/calendar](https://www.nyse.com/markets/hours-calendars)
- [IBKR historical market data](https://ibkrcampus.com/docs/web-api/v1/endpoints/market-data/historical-market-data)

No premium vendor integration has been purchased or silently switched into the original strategy. State Street SPY ETF holdings may help as a second check, but **they are not automatically an official historically effective S&P 500 index constituent record** and cannot substitute unnoticed.

## What this branch actually implements

1. `dual_momentum/gem_source_probe_2026_10_12.json` records six dated source diagnostics, each PARTIAL, with actual limited-scope findings and specific unresolved gaps. `gem_source_evidence.py` strictly validates the schema/ref, drops future/duplicate probes, enforces expiry (2 days for prices and SPY), and **downgrades any unauthenticated VERIFIED claim** to PENDING_QA. The dashboard displays evidence, scope and gaps, and always shows **0/6 independently certified**.
2. `gem_data/coverage_gate.py` independently recomputes a proposed full-universe r63, ADV20, six-fact revenue/earnings/margin gates, rank, and complete-name coverage. Production minimum 480 security/share-class lines is conservative, **not** a claim that the index always contains exactly 500 rows. Missing competitors, untimely filings, missing period/context, invalid quotes, unmapped price adjustments, corporate-action/benchmark/calendar gaps **HOLD**. Output is an unauthenticated review proposal; it never grants paper execution. The role-separated, signature-bound reviewer and raw-SEC parser are still required for deployment.
3. `scripts/gem_public_source_diagnostic.py` makes bounded read-only requests to **two secondary public constituent/history lists** and NYSE hours; it records response byte hashes, retrieval times, row/CIK counts and limitations. The CI workflow runs it and stores a temporary downloadable artifact for investigation. It does **not** publish its output as trade data, query a broker, access DM database or overwrite existing files. All findings are availability-only.
4. Dedicated tests cover full-universe omission, future SEC acceptance, custom fact ambiguity, missing vendor parity, stale source evidence and forged VERIFIED claims, alongside existing paper-trial regression tests.

## Remaining work before any new GEM order

**G1 — Complete collection:** Obtain original official-effective S&P membership or an explicitly agreed alternative universe (which would require separately versioning the strategy); build a restricted unattended IBKR market-data bridge in an isolated service; run a rate-limited SEC accession/XBRL collector over the complete universe; separately collect and reconcile all effective actions; qualify official next-open calendar and SPY total-return. Raw receipt hashes, local observation timestamps and coverage manifests must be persisted in dedicated **GEM-only Neon** tables without touching the Dual Momentum database.

**G2 — Independent QA:** Data collector must not approve its own snapshot. A separate verifier with independently controlled credentials recomputes all candidate evidence and frozen monthly signals, validates original raw files/time semantics, emits authenticated per-check QA certificates bound to the signal/input/portfolio/code digest and expiry. The current coverage gate is deliberately only an offline verifier, **not** final production QA.

**G3 — Release:** Shadow one genuine new month-end plus 20 completed sessions under the original safety plan, reconcile a simulated next-open preview with 20bps side costs, run failure/retry/recovery drills, and obtain explicit user signoff before a separately reviewed simulator can book paper orders. No brokerage order route is ever used.

## Historical research alignment

Sept 30 archived GEM top-five: P, MPC, PLTR, HPE, VLO; **20 competing date/security cases unresolved**, especially PSX (above the observed fifth selected r63), FDXF and HONA (unknown momentum). Historical certification of the broader 943 cases remains a separate independent workstream. A later correction must be versioned and must not rewrite prospectively recorded selections.

The October 1–9 +12.85% account on the dashboard is a *retrospective reference only*, not a certified forward result. The GEM Neon project `gem-v1-forward-paper-isolated` remains independent from the Render PostgreSQL DB scheduled for Nov 5 expiry. It already stores two disabled/shadow experiments and the backfill daily observations. The dashboard's least-privileged Neon reader account was created/checked but secure credential setup in Render is **not yet completed**; source states are therefore bundled dated diagnostics, not an operating live feed.

## Agent ownership / handoff

**Universe & identity:** deliver official dated member manifest and issuer IDs.
**Market data & actions:** deliver all-member OHLCV, nominal adjustment chain, corporate-action and stale-bar receipts.
**SEC fundamentals:** deliver source-file hashes, timestamped accession-specific six-quarter gate facts and both pass/fail/unknown outcomes.
**Calendar & SPY:** deliver exact month-end/next-open schedule and benchmark cash/marks.
**Ranking:** consume only complete sealed manifests, recompute independently and seal targets.
**QA (separate identity):** reconstruct data/gates from originals, approve or HOLD with explicit unclosed cases.
**Storage/ops:** durable GEM-only receipts, telemetry, retries, reconciliation, recovery; never share DB or overwrite DM.
**Historical-certification agents:** review 943 cases without contaminating the forward snapshot.

Acceptance is **six separately supported VERIFIED certifications and a separately reviewed QA PASS**, not six successful HTTP pings or manually edited yellow badges.
