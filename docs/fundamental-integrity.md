# Fundamental source and calculation integrity

Production scoring version: `2026-10-06-current-sec-aliases-v15`.
The canonical dashboard and single paper strategy use the same scorer.
The scoring bands, 20-point fundamental cap, neutral unavailable baseline,
qualification gates, allocation bands, fees, exits and trial clock are preserved.

SEC calculations use USD facts and real start/end dates. Annual growth matches
adjacent fiscal years, including 52/53-week calendars. Numerators for margins
and cash conversion must match annual revenue's dates. A later annual filing
with missing revenue cannot silently use an older year. Quarterly revenue YoY
retains the previous same-quarter and conservative Q4 derivation logic.

ROE is annual GAAP net income divided by average equity at the beginning and
end of that fiscal year. Missing or nonpositive equity endpoints leave ROE
unavailable. It must not mix annual income with newer quarterly equity.

Earnings growth means reported net-income growth for SEC, not EPS or adjusted
income. A zero or negative prior-year base leaves percentage growth unavailable;
loss improvement, loss deterioration and a return to profitability are stated
separately and do not get fabricated percentage-growth points. Actual 0% growth
is preserved, and Yahoo forecast growth is stored separately from actual growth.
GAAP total income can contain discontinued operations and exceptional gains;
this is explicitly labelled and is not represented as recurring-profit growth.

Debt uses a single balance-sheet date. Total tags replace overlapping maturity
tags; current totals replace overlapping short-borrowing/current-long-debt tags.
Distinct short borrowings and long-term components are added once. Aliases use
the latest filed fact for that date. Explicit zero is a valid number. Incomplete,
stale or negative components, or nonpositive equity, leave the ratio unavailable.
An obsolete short-borrowing series without a current observation cannot be
assumed to be zero. This can lower scores through missing credit; it is disclosed
rather than inventing a complete debt amount. Company-specific/custom XBRL tags
outside the supported standard taxonomy remain a coverage limitation.

When this verified SEC block exists, missing/rejected values are not refilled
with Yahoo values from unknown periods. Other pricing, analyst and valuation
fields retain their independent sources. If SEC is unavailable, reported Yahoo
metrics can still be used with their provider provenance; forecasts never stand
in for actual earnings growth. Nonfinite or malformed numbers do not count
as observed fundamental evidence or crash scoring.

The detail page labels the annual period, income definition, ROE method,
balance-sheet date, unavailable metrics and any subtotal reduced by the 20-point
cap. A new scoring version refreshes old stored analyses. Fundamentals from an
older scoring version cannot be used as evidence of company deterioration.

Income aliases are now selected by a matching current annual start/end period,
and equity aliases by their latest eligible balance-sheet observation. An old
preferred concept cannot hide a current alternative concept. Growth comparisons
stay within the selected concept; missing prior-year data is never stitched from
another alias. Valid zero/negative values retain their existing scoring treatment.
The Broadcom SEC fixture reproduces obsolete NetIncomeLoss (last annual 2024)
and StockholdersEquity (last balance 2019), while ProfitLoss and equity including
noncontrolling interests remain current. Matched source arithmetic restores
292.3% earnings growth, 31.0% ROE and 59.6% debt/equity. Existing fundamental
bands yield 12 → 20; unchanged other components give 50 → 58, still below 70.

The export and detail page separate unavailable exact inputs from observed weak
values. Financial-services issuers are explicitly labelled as subject to the
existing industrial margin/debt scoring limitation. This release does not add
a sector-specific financial model or normalize incomplete inputs into full credit.

Validation includes adversarial dates/units, positive and negative equity,
profit/loss transitions, zero/missing debt, overlapping debt tags, stale aliases,
restated facts, preserved scoring bands, and SEC-derived CRDO/WDC/MSFT/NVDA
source fixtures retrieved on 5 October 2026. An unchanged-input CRDO replay
moves fundamentals 19 → 20 and total score 59.8 → 60.8; this is not a prediction.
