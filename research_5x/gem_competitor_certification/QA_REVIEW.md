# Independent QA: frozen GEM competitor certification

Reviewed 2026-10-11. Scope: isolated research acquisition, retained-source parsing, queue/impact calculations and review-envelope scaffold. **Verdict: research evidence only; all 943 full cases remain open.** This workstream cannot authorize a trade, change GEM V1 or certify investment returns.

The full frozen base is `d59b93d3d9a87d582045b4ae71ff9a6f696a48be`. Source hashes and the exact nine-file archive lock are verified before deterministic triage. The 943 security/date case keys are unique and remain `EVIDENCE_REQUIRED`; names/CIKs are archived identities awaiting complete historical lineage. A retained fact-value/timing match is cache consistency, not full eligibility certification. The controlling prospective gates remain the [separate forward QA/release design](https://github.com/ankitgarg1234-cell/isk-trading-radar/blob/research/gem-forward-safety-2026-10-11/docs/gem-v1/QA_AND_RELEASE.md); historical research certificates cannot satisfy those gates by implication.

## Queue and conditional impact

The frozen queue spans 21 signal dates and 111 tickers: 137 rows above the archived selected momentum cutoff, 147 with unknown momentum, three able to fill an archived empty slot and 656 below cutoff under fixed archived selected values. Triage does not use subsequent returns, financial thresholds are not tuned and unknown momentum is not zero.

The conditional observed-momentum scenario totals at most 29 changed target slots across dates; allowing unknown momentum to outrank observed candidates totals at most 92. These are set bounds assuming the archived selected rows remain fixed and every backlog row qualifies. They are not probabilities, certified substitutions, dollar effects or return bounds. The lower bound is zero; return impact remains unknown until source-complete certified selections and unchanged-rule portfolio replay exist.

## Independently checked original SEC bytes

The reviewer independently recomputed SHA-256 for all three retained original headers and the one acquired AWK XBRL instance, then checked header accession/CIK/form fields and quarterly XML contexts rather than trusting the generated report. The retained header interpretation is:

| Security / sample date | Original acceptance digits | UTC under declared New York convention | Cached SEC UTC | Cached minus interpreted |
|---|---|---|---|---|
| NEM / 2025-03-31 | `20241024161313` | 2024-10-24 20:13:13 | 2024-10-24 20:13:13 | 0 |
| LLY / 2025-02-28 | `20241030115410` | 2024-10-30 15:54:10 | 2024-10-30 19:54:10 | +4 hours |
| AWK / 2025-03-31 | `20241030163027` | 2024-10-30 20:30:27 | 2024-10-31 00:30:27 | +4 hours |

These discrepancies are conditional on the declared daylight-aware New York interpretation, not certified corrected timestamps. The [official SEC FAQ](https://www.sec.gov/files/about/webmaster-faq.htm) describes acceptance time as EST, gives no first-public-availability timestamp and does not guarantee dissemination lag. A literal fixed UTC−5 interpretation would differ by one additional hour: NEM −1 hour and LLY/AWK +3 hours versus cached values. Both conventions put these three acceptance dates months before their sample signals, but neither establishes exact first public availability. The report correctly keeps timezone interpretation as inference and `proves_first_public_availability=false`.

The independent AWK XML extraction tied issuer CIK 1410636, consolidated nondimensional contexts c-5/c-6, USD units and exact quarter periods to these original values:

| Quarter | Consolidated regulated/unregulated revenue | Operating income | Net income |
|---|---|---|---|
| 2024-07-01 to 2024-09-30 | $1,323,000,000 | $543,000,000 | $350,000,000 |
| 2023-07-01 to 2023-09-30 | $1,167,000,000 | $478,000,000 | $323,000,000 |

Two revenue-period values match four archived input uses across March/April 2025. This resolves the narrow numeric discrepancy using `RegulatedAndUnregulatedOperatingRevenue`; semantic mapping still requires the independent reviewers and complete latest-filing/period-selection proof. Based only on these periods, revenue growth is approximately 13.3676%, net-income growth 8.3591% and margin improvement 0.08336 percentage points, below the frozen three gates. This is an observed-period diagnostic, not a full certified exclusion. NEM/LLY XML acquisition remained bounded by the declared response-size limit; failures are retained and no values are inferred from them.

## Independent findings and certification boundaries

| Finding | Resolution / retained limitation |
|---|---|
| Same accession/end/value can conceal a different quarter start | Exact direct period-start match now required; mismatch/absence remains unresolved; derived quarters need separate dependency lineage |
| Complete quarter/context/filing/latest selection cannot be proved by retained minimal aggregates | Original raw facts, contexts, complete eligible filing set and frozen comparator selection remain mandatory |
| Acceptance timestamps differ under the declared New York convention | Preserve both raw/cached values and declared inference; no silent normalization or public-availability certification |
| Early acquisition metadata called request-start time retrieval | Preserve original records with explicit note; subsequent acquisition separates request/completion/observed timestamps |
| Conflicting consolidated original values must not be selected by dictionary overwrite | Corrected: conflict key uses the local tag, exact start/end and normalized USD, including namespace/unit-prefix aliases; regression tests reject differing values and deduplicate equal observations |
| Exact comparisons and derived diagnostic claims must be literal | Corrected: exact Decimal equality, evidence-derived matching-period count and exact frozen positive-income/nonpositive-comparator earnings rule; boundary and fractional-disagreement tests pass |
| Primary report must not look up replaced historical inputs | Corrected: full frozen-input lock enforcement runs before the primary source review; drift remains a blocker |

The structural certification envelope requires a collector and two distinct reviewer identities, all proof checks and agreeing reproduced results. It cannot authenticate identities or evidence truth and is not a mechanism for automatic terminal-state persistence. Generated local hash-linked events are tamper-evident artifacts, not immutable storage or an independent trusted anchor.

Remaining full-case requirements: primary historical universe/identity/action/price lineage; exact filing/publication and fact context/units; complete latest-period/comparator proof; two authenticated independent reviews; sealed evidence and reproducible unchanged-rule ranking/portfolio impact. Every case remains open until all required proof exists.

## Final verification

Independent execution of `python3 -m unittest discover -s tests/gem_certification -v` passed **27 offline tests** on 2026-10-11. Coverage includes wrong accession/period start/pretax mapping, signal-day and naive acceptance timestamps, manifest drift, missing momentum/cash slots/stable ties/five-slot bounds, two distinct reviewer envelopes and agreement, forbidden certification jumps and append-only revocation, event-chain corruption, deterministic frozen artifact reproduction, conflicting headers and normalized XML values, literal numeric equality, frozen loss-to-profit earnings behavior and original-instance document discovery.

The reviewer independently rebuilt the queue and primary review without network calls: all generated queue artifacts matched their committed candidate bytes in the integration test, and the primary report matched parsed JSON exactly. Rebuild retained 943 open cases, 1,572 cached accession/value/time matches and 142 unresolved cached uses; no full case was certified and return impact remained unknown. Three headers plus one original AWK XML instance passed independent raw-byte hashes; CIK, periods, consolidated contexts, USD units and the six diagnostic financial values were manually cross-checked by independent extraction.

No unresolved high-severity defect was identified within this bounded offline research scope after the requested corrections. This conclusion does not certify a complete point-in-time universe, public-availability timing, generalized XBRL engine, reviewer authentication, immutable storage, portfolio impact or prospective release. No trading, deployment, production/live-position access, automatic case closure or strategy tuning occurred during this independent review.
