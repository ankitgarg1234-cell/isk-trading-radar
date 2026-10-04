# News relevance and context correction

The revised dashboard scoring version is `2026-10-04-news-context-v6`;
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

The locked one-month trial consumes `legacy-v1`, including the original complete
score, catalyst calculation, target geometry and R/R, computed from the same
provider bundle without another fetch. Its compact input is transient and never
creates another account. A revised analysis without a locked input is rejected
by the trial adapter. Dashboard snapshots record old/revised score comparisons.
No accounts, cash, holdings, experiment clock or thresholds are reset.

The model version invalidates older candidate scores through the existing cache
refresh path. The detail page displays grouped events, evidence directions,
point adjustments, duplicate/exclusion counts and headline-only confidence.

Validation: 113 news, model, trial and balance checks passed, including 34 new
news-context checks. A broader run passed 160 checks and reproduced the same
four existing scanner and eight existing dashboard failures. The four scanner
failures were independently reproduced on the unchanged deployed baseline;
the eight dashboard failures were already reproduced before the month trial
deployment. Five full scoring scenarios matched the unchanged frozen model
exactly, including score, targets, lane classification and R/R.

A live CRDO feed sample on 4 October returned 15 headlines. The old news score
was 15/15; the revised score was neutral 7.5/15, with four excluded headlines
and no unambiguous rule-matched company event. This illustrates the correction,
not a conclusion about CRDO fundamentals or its future returns.
