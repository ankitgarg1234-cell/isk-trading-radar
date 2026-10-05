# Scanner coverage repair — 5 October 2026

Production cycle at 15:33:14 UTC listed 5,758 equities, quick-scanned 200 and queued 44 candidates, but analyzed only 32. The effective batch calculation counted configured discovery quotas but omitted extra stale-score/dirty-news refreshes. Rotating broad candidates at the tail could therefore be discarded. All 32 consensus targets were unavailable and 13 P/E values were missing; no inference about qualification across all 5,758 names is supported.

## Repair

Size the full-analysis batch from the actual deduplicated queue, preserving the existing 48-analysis per-cycle resource ceiling. Carry overflow ticker strings into subsequent cycles before new discoveries, keeping current holdings first. Report queued and deferred counts explicitly.

Advance the quick-scan universe cursor from the batch actually attempted, so long cycles cannot skip wall-clock slots. A fresh process initializes near the current session slot; cursor state is process-local. This guarantees sequential quick-scan traversal during uninterrupted operation, not a full fundamental assessment of every listed equity.

No score changes, gate reductions, ledger reset, trial-date changes or subscription changes. Consensus price targets still require provider access; HTTP 403 remains unavailable.

## Validation

Regression cases cover the observed 44-to-32 truncation, overflow carryover, holdings priority and deduplication, consecutive slices within one time slot, and full 5,758-name quick-scan traversal in 29 batches. Focused checks also cover the shared 0.4x gate, 70/75 thresholds, paper state, fundamentals and RVOL.

Release checks: 177 focused tests passed. Full suite: 426 passed, the same 27 failures as the prior baseline; no new failures. Dashboard universe tile now explicitly labels listed stocks.
