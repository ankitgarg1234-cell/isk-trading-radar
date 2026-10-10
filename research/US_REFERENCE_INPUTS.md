# U.S. baseline and reference-input investigation

Checked10 October2026. Source work is complete; executable inputs remain
BLOCKED. No public constituent candidate is promoted to a verified baseline.

The source already used by `dual_momentum/data.py` was retrieved from
https://raw.githubusercontent.com/lawcal/sp500-components-history/main/data/components_history.csv
with its MIT license and README. It has1005 effective-date records through
October6 2026. Naive September29 2023 filtering gives512 symbols. Applying
the source's creation-date safeguard removes eight future aliases, leaving
504 symbols/500 issuer CIKs. FI/FISV remains an overlapping ticker pair;
FOX/FOXA,GOOG/GOOGL,NWS/NWSA include real share classes and are not deduplicated.
Eleven retained rows contain starred/approximate dates. The README explicitly
warns that ticker ranges may overlap and it does not model ticker changes.
Publication/announcement timestamps and independently verified security
identities are absent. Do not certify504 symbols or remove an alias by guess.

A separate503-row current dataset explicitly labels GICS Sector:
https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv
Its package declares ODC-PDDL-1.0; its data source is Wikipedia.448 of504
prelaunch candidate rows match one current sector by issuer CIK (88.89%).
These are issuer-level research candidates, not verified historical sectors or
security/listing joins. The permitted exploratory fallback requires documented
source/typed identity/corrections. No current membership list fills historical
gaps and no ambiguous share-class/issuer link is silently accepted.

The official SPY product page returned HTTP200 and exposes public links to
`pdhist-us-en-spy.xlsx`, `navhist-us-en-spy.xlsx` and daily holdings. Their
contents were not imported. NAV/fund performance is not daily equity OHLCV
and cannot replace ATR/stop/fill inputs. The page restricts reproduction/
third-party disclosure; downloaded raw data must not be committed. Validate
permitted research use and exact historical field/adjustment coverage before
importing official spreadsheets. No12-reference completeness claim is made.

The cached539 stock series still have a maximum211 prelaunch bars; none
passes253. SPY and all11 original sector ETFs are absent. EODHD's known Free
entitlement cannot supply2021–26. Yahoo terms retrieval failed with proxy403;
no new Yahoo price request was made without confirmed permitted automated
research use. Existing code that calls a provider is not an entitlement.

Required resolution: reconcile dated S&P announcements or a licensed/
rights-permitted membership export including the September2023 initial set;
verify alias/listing transitions; supply complete daily stock/reference raw
OHLCV, separate adjusted/TR closes and actions from approximatelyJanuary2021
throughSeptember2026. Current-GICS source fallback is allowed only with the
new explicit provenance/coverage policy. Exact public evidence, licenses and
checksums remain under ignored `historical_backtest/reference_sources/`.

`python -m research.us_reference_audit` recomputes the candidate audit offline.
Three regressions cover future aliases, real share classes and conflicting
current issuer sectors. Baseline/reference readiness remains FAIL.
