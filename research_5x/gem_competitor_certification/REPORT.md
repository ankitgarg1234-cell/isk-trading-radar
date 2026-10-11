# Historical certification progress — October 11, 2026

Frozen source: `d59b93d3d9a87d582045b4ae71ff9a6f696a48be`, the named GEM V1 validation branch. All source files remain unchanged. This work performed an independent cached evidence review and bounded new primary SEC acquisition. **No full competing-security/date case is newly certified; all 943 remain open.**

## Observable displacement risk

| Backlog classification | Cases | Meaning |
| --- | ---: | --- |
| Above that date's lowest selected observed r63 | 137 | Could outrank at least one archived choice if the missing eligibility gates pass |
| Unknown momentum/price | 147 | Ranking effect cannot be bounded from the missing observation alone |
| Positive score below cutoff with archived cash slots | 3 | April 30, 2025 selected three securities, so additional eligible names can fill cash |
| Below the fixed observed selected cutoff | 656 | Defer displacement work while keeping evidence requirements open |
| Total | 943 | 111 tickers across 21 monthly signal dates |

Conditional re-ranking of all positive observed backlog momenta gives a 0–29 aggregate upper bound on changed target-slot observations across those 21 dates. Allowing unknown momenta to outrank every observation raises the conditional range to 0–92. These are repeated date/slot observations, not unique securities or portfolio losses. They assume all backlog cases qualify and the archived selected candidates and price units are correct. Actual return impact remains unknown; no future returns enter priority or these bounds. Per-date hypothetical sets and assumptions are retained in `artifacts/date_impact_bounds.json`.

The first review cases are NEM/ED/EXC/WELL/AEP on March 31, 2025, then FOX/LLY on February 28, 2025. These priorities come from the number of archived selections their contemporaneous momentum outranks and the score gap, not subsequent performance. March 31 NEM's archived r63 is 26.7524% versus the lowest selected 2.7514%; its missing operating-income evidence still prevents eligibility certification.

## Independent retained-cache review

1,714 backlog input uses were independently parsed. 1,572 match retained accession/CIK, exact quarter start/end, eligible 10-Q form and duration, value, source-manifest hashes and retained acceptance cutoff. 142 remain unresolved; prior labels comprised 106 missing direct quarters, 20 acceptance failures and 16 value mismatches. Independently computed errors include 122 missing timely matching direct quarters and 88 absent acceptance timestamps, with overlap. Cached matches are **consistency observations**, not verification that the original raw API response, complete filing set, historical identity, universe or price lineage has been certified. All cases remain `EVIDENCE_REQUIRED`.

## New primary evidence and findings

Three original accession headers were acquired and retained with raw-byte SHA-256 hashes:

| Security/accession | Raw ACCEPTANCE-DATETIME | UTC under declared America/New_York interpretation | Prior cached UTC |
| --- | --- | --- | --- |
| [NEM 0001164727-24-000061](https://www.sec.gov/Archives/edgar/data/1164727/000116472724000061/0001164727-24-000061-index-headers.html) | 20241024161313 | 2024-10-24 20:13:13 | 2024-10-24 20:13:13 |
| [LLY 0000059478-24-000245](https://www.sec.gov/Archives/edgar/data/59478/000005947824000245/0000059478-24-000245-index-headers.html) | 20241030115410 | 2024-10-30 15:54:10 | 2024-10-30 19:54:10 |
| [AWK 0001410636-24-000187](https://www.sec.gov/Archives/edgar/data/1410636/000141063624000187/0001410636-24-000187-index-headers.html) | 20241030163027 | 2024-10-30 20:30:27 | 2024-10-31 00:30:27 |

LLY/AWK therefore differ by four hours under the declared timezone interpretation. NEM agrees. The [SEC FAQ](https://www.sec.gov/files/about/webmaster-faq.htm) describes header acceptance time as `Time (EST)` and explains that first sec.gov availability has no exact timestamp and can follow acceptance after a variable lag. Its literal EST wording does not settle the daylight-saving convention: the America/New_York normalization above is explicitly an inference/configuration, not a definitive finding that the cached data is wrong. `primary_review.json` also preserves a literal fixed UTC−5 interpretation, under which the cached-minus-interpreted differences become +3 hours for LLY/AWK and −1 hour for NEM. All timestamps in either interpretation precede these three target signals by months. This sample does not certify publication availability for cases near a cutoff. Preserve both original representations and quarantine unresolved timezone/publication disputes.

The original [AWK XBRL instance](https://www.sec.gov/Archives/edgar/data/1410636/000141063624000187/awk-20240930_htm.xml) was also acquired (1,604,194 bytes). Consolidated USD contexts with exact July–September periods contain `us-gaap:RegulatedAndUnregulatedOperatingRevenue` of $1.323 billion (2024) and $1.167 billion (2023), exactly the archived TotalRevenue inputs. The earlier minimal audit used a different revenue concept (`RevenueFromContractWithCustomerIncludingAssessedTax`: $1.328/$1.170 billion) and marked the archive values mismatched. The original accession supplies a concrete semantic-mapping explanation for two distinct revenue periods/four input uses on the March 31 and April 30, 2025 backlog dates. The mapping remains pending both independent semantic reviewers; the frozen engine and aliases were not changed.

Using those original-quarter values, the observed frozen revenue growth is 13.3676%, net-income growth is 8.3591%, and operating-margin improvement is 0.08336 percentage points. All three observed GEM gates fail. This supports a provisional failure explanation for the two dates if this accession/quarter is independently established as the correct frozen latest-period selection. Complete filing coverage, selection provenance, primary historical membership/identity and two independent certification decisions remain missing, so the case status stays open. No performance impact was fabricated or calculated from this sample.

NEM/LLY XBRL downloads exceeded the strict 2 MB response cap; their failures are retained instead of silently increasing limits. Initial sandbox DNS failures and standalone-Python certificate failures are also retained. System TLS trust then acquired the three headers and AWK instance with certificate verification enabled. Primary evidence spans **three distinct original accessions, four successful raw documents, two timezone-provenance discrepancies, and two new revenue-period semantic reconciliations; zero full case certifications**.

`artifacts/primary_review.json` reproduces the header parsing, declared timezone assumptions, source hashes, consolidated AWK contexts, period/value comparisons and remaining failures. Request-start timestamps in the initially generated acquisition envelopes were originally labeled `retrieved_at_utc`; those original envelopes are preserved and the review notes their semantics. Updated acquisition code records request start and completed retrieval separately. These October 2026 retrieval times are never presented as historical first availability.

## Next bounded milestones

1. Obtain reviewed NEM/LLY original instances using a documented larger bounded response cap; retain accession-specific semantic facts and derivations. Resolve missing operating income without substituting pretax income.
2. Have two distinct financial certifiers independently review AWK's complete original filing set and regulated-revenue mapping; only then append any terminal decision or revised conditional impact scenario.
3. Reconstruct historical issuer/share-class/membership lineage and removed-name prices for the 147 missing-momentum cases; explain AVB's nonstandard vendor factor before using its prices.
4. Resolve the highest 137 observed cutoff competitors, plus cash-slot cases, with complete contemporaneous filing selection/publication proof. Reproduce affected ranks with unchanged GEM V1 gates and stable ties.
5. Run a frozen counterfactual replay only after decisions and price/action evidence pass independent QA. Report changes to selected sets, orders, turnover, costs, cash, drawdown and P&L with limitations; publish no return-impact claim earlier.

No deployment, production files, existing positions, paper purchases or real-money orders were touched. The case workflow is a research scaffold; it cannot authenticate reviewers or make a local hash chain immutable. Release gating for the parallel forward paper trial remains separately fail-closed and requires the user's later explicit signoff.
