# News relevance and context correction

The canonical scoring version is `2026-10-04-single-paper-v7`;
the news assessor is `headline-context-v2`. This change addresses explicit
company relevance, repeated event coverage, overlapping word matches,
negation, speculation and mixed positive/negative reports.

Yahoo search preserves its `relatedTickers` metadata. Headlines must identify
the ticker/company or carry an unambiguous single-ticker provider association.
Short ticker matches require uppercase spelling. Unrelated and future-dated
articles are excluded and remain visible in the audit section.

Fixed event patterns replace substring counting. Each event type/direction
counts once, up to two weighted signals per grouped event. Questions,
speculative language and generic hype receive no positive event credit.
Negation suppresses the asserted event. Mixed reports receive no bullish
bonus and preserve their adverse evidence. Other explicitly named company
clauses cannot supply the target company's event credit where clause scoping
identifies them.

Exact headline/URL duplicates are grouped; known dates more than 36 hours
apart remain separate. Approximate earnings/guidance/rating grouping requires
matching event categories, fiscal-period markers and publication times within
36 hours. Other events require close headline similarity. This is conservative
headline grouping, not proof that two releases are identical. Separate contracts
and separate fiscal quarters must remain separate.

The 7.5 neutral baseline, publisher weights, 0–15 bounds and age policy are
preserved. An unavailable feed is labelled unavailable, with its retained
baseline explicitly disclosed. Changing the baseline or applying age decay
requires a separate calibration change. No extra provider, AI API, article-body
scraping or credentials are introduced. Ambiguous unmatched events remain
unscored; the assessor does not verify full articles or financial figures.

There is one scoring path. The dashboard and canonical paper strategy receive
exactly the same corrected analysis, including news, deterministic score,
analyst score, targets and R/R. No legacy news model or alternate trial score
is computed. Observations retain their scoring version for auditability.
The agreed paper ledger is the dashboard's active paper account. When the
trial is armed, the old Top-20 engine cannot execute or accept manual paper
trades, and its reset endpoint cannot alter the active ledger. Existing old
rows are preserved. Run-now invokes the scanner and agreed execution path.
Cash, shares, clock and thresholds are preserved; production's trial was
waiting for inputs with no trades when this correction was authorized.

The model version invalidates older candidate scores through the existing cache
refresh path. The detail page displays grouped events, evidence directions,
point adjustments, duplicate/exclusion counts and headline-only confidence.

Validation covers single-score delivery, corrected observation capture,
account projection without a second ledger, disabled old execution and
preservation of quantities, balances and trial clock.

A live CRDO feed sample on 4 October returned 15 headlines. The old news score
was 15/15; the revised score was neutral 7.5/15, with four excluded headlines
and no unambiguous rule-matched company event. This illustrates the correction,
not a conclusion about CRDO fundamentals or its future returns.
