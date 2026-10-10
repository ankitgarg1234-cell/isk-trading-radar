# Corporate-action and inactive-security readiness

Step7 is BLOCKED for real-data completeness, with independent accounting
adapters/tests completed. None of the21 original portfolios or inactive
security observations was filtered by present survival. Raw data is preserved.

The legacy539-series cache contains splits for51 series and dividends for429.
Split rows containdate,numerator,denominator,ratio; dividend rows containdate
andamount. They do not establish complete announcement/payment times,share
basis,currency,net/gross convention,merger consideration or delisting recovery.
A date/amount pair cannot create an assumed cash payment. AZN/Korean rebound/
Taiwan closure logic and all earlier regression evidence remain intact.

New optional `CashDividend` accounting uses source-proven ex/pay/available
times,amount per applicable share,currency and source. Entitlement is captured
before ex-session orders after applicable share transformations. It survives
a later sale; buying on/after ex-date does not earn that entitlement. Unpaid
claims are valued as receivables with observable FX,not spendable cash; actual
payment transfers them to cash. Original selection/sizing formulas use
economic NAV; cash affordability still uses actual paid cash. TR affects
ranking separately; rawOHLC/price NAV plus receivable/income avoids double
crediting dividends. Stock/sector cash-flow attribution includes receivables
and payments and reconciles NAV. No automatic reinvestment rule is introduced.

Both historical bundles must explicitly declare the same `dividend_policy`:
`SOURCE_VERIFIED_NET` or `SOURCE_VERIFIED_GROSS_NO_WITHHOLDING`. The latter is
a disclosed gross accounting convention,not an invented tax calculation.
A fixture/direct engine with no dividends retains the original ledger behavior,
and existing US synthetic parity is unchanged. Price-only FIFO lot win-rate
statistics do not allocate dividend receipts to individual closed lots;
aggregate stock/sector attribution includes income.

`cash_dividends` rows: symbol,ex_at,pay_at,available_at,amount_per_share,
currency,source. Evidence must establish the applicable share coordinate and
actual dated payment/entitlement; duplicates/restatements and future-known
entitlements fail. Currency conversion is source-timed and positive. Do not
use vendor adjusted_close/close as a split-onlyOHLC factor.

Material event inventory must be supplied in `material_corporate_events`.
Split/share representation and cash-dividend events have adapters; a declared
material merger,delisting or recovery currently fails admission explicitly.
A `complex_actions_resolved` evidence file cannot override that unsupported
runtime event. Required resolution includes effective/public dates,old/new
identifiers,cash/stock consideration,depository/share ratios,valuation through
suspension,receivable settlement and verified fractional cash-in-lieu. No
last price,zero recovery,stock substitution or future liquidation is guessed.
An inactive price may be omitted only with documented lifecycle/eligibility
and complete held-position accounting; surviving-only histories remain invalid.

45 focused action/closure/engine/metrics tests passed before the final full
suite. Four new dividend regressions demonstrate earned entitlement after a
sale,no entitlement after ex-date,future/duplicate rejection,and exact NAV
reconciliation through an ex-price drop and later payment. These are synthetic
accounting evidence,not a claim that missing real action data are resolved.
