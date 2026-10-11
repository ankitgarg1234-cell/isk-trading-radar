# Point-in-time data audit

**Fail for the requested validation.** Hash-valid source snapshots establish provenance of what was read, not historical truth of the underlying inputs. The user's response confirms no alternate certified data or original-control archive is available.

| Required input | Available evidence | Finding and consequence |
|---|---|---|
| Exact original A | Reconstructed 75/25 source and failed reconciliation | Do not substitute; no original trades/NAV to reproduce |
| Full 2022–2023 broad universe/fundamentals | Adaptive replay source/results; phase-2 earlier public-price probe | Proxy reconstruction is not certified; phase-2 probe is 12 selected live series, with WBA/PXD downloads missing |
| Historical membership | Reverse reconstruction from current constituents/change lists | Effective/announcement timestamps and security/issuer aliases not fully certified; archive explicitly flags false |
| Delisted securities | 16 failed price symbols excluded in frozen broad cache | Missing delisting/merger consideration can bias selection and NAV; last quotes are not settlement values |
| Raw prices and splits | Vendor daily bars plus action lists | Algebraic split-unit restoration can be legitimate, but requires an independent equivalence audit; nonstandard synthetic ratios are uncertified |
| Spinoffs | WDC/SNDK, GE/GEV, MMM/SOLV adjustments | Source-confirmed distributions still lack complete contemporaneous raw-price/basis/cash-in-lieu treatment; missing actions outside these names unresolved |
| Dividend cash availability | Ex-date amounts | Credit a receivable on ex-date and actual spendable cash only on payable date; archived early cash availability is unacceptable for certification |
| Original accounting vintages | Filing-dated provider facts; manual source reconstruction for MU/STX/WDC | Broad panel not audited to original accessions; derived quarters and accounting scope may be revised or mismatched |
| Actual publication timestamps | `accepted_at` stored, filing-date admission | Accepted time is used for tie ordering, not the admission gate. The one-day lag is conservative for many filings but does not establish actual availability or earliest release evidence |
| Analyst estimates | Explicitly absent | No historical surprises/revisions/expectation exits; reported improvement is not consensus acceleration |
| Historical sector/industry maps | Current sector map, no industry history | Improving-industry rankings and industry contribution/concentration cannot be reconstructed correctly |
| Realistic execution | Daily opens; 7/20 bps heterogeneous archived engines | No shared certified A–F assumptions; absent spreads, capacity fills, overnight stop behavior, trading halts and marketability checks |
| Unseen data | Archive explicitly false | Freezing now does not undo prior examination of 2022–2025 or 2026; repaired runs remain retrospective |

## Date availability versus data lookahead

Every future signal must reference immutable source IDs/hashes and **available_at < signal_timestamp** for prices, fundamentals and classification inputs. Use actual release or SEC acceptance timestamps with time zones; `period_end` never represents publication availability. If only filing dates are available, the conservative usable timestamp must be explicitly defined and the original-file vintage audited, or the record stays ineligible. Later restatements may be used only after their own publication. For multi-input scores, available_at is at least the maximum of all constituent timestamps; derived facts inherit all source dependencies. An assumed lag is not evidence of a missing historical industry map or missing delisting proceeds.

Prices must end with the preceding completed session under the user's before-signal-date rule. Execution timestamp must strictly follow the signal, with explicit market session and raw fill prices. Corporate actions must preserve economic ownership and be posted when effective; membership changes need their contemporaneously known announcement/effective dates. Future outcome columns must live outside the signal/ranking input table. Subsequent outcomes are joined only after immutable decisions are persisted.

The archive's `prepare` routine contains forward labels alongside input features. Its documented simulation selects from trailing columns, so the presence of labels alone is not proof of lookahead. A new certified pipeline should prevent future-labelled columns from reaching ranking functions and test prefix invariance. No such new signal certification was run here.

## Acquisition and coverage record

The attached `/workspace` had no research files. The connected GitHub repository's main branch has no `research_5x`. The October 11 archive was recovered at phase-2 commit `4ea44011e3911227f9be2266d5dcb6c078b8722a`; adaptive reconstructions at `c4bb696e61acf5d77ea6a18aada4cd58e998f83f`. Branch names alone were not treated as provenance: `research/regime-ablation-75-25` currently points at an unrelated paper-PnL reconciliation commit. Git cloning failed because the workspace proxy was unreachable; native GitHub connector reads succeeded. No credentials were printed or alternative network route used.

Twenty-seven exact source snapshots were checked against Git blob hashes and SHA-256 manifests. The original October 11 ZIP and its complete 1,144-member audit are not present, so that earlier archive verification is an inherited claim, not a new verification. The broad frozen panel inventory has 16,257 rows, 533 tickers, January 2024–September 2026; 10,275 mature labels, 188 qualified mature rows, 58 qualified losses. These 252-session price-only labels are not portfolio annual returns.

Requested account results are missing, explicitly blank, not synthesized as zero-return cash portfolios. No data-availability audit for every historical signal can be completed because those certified signals do not exist.
