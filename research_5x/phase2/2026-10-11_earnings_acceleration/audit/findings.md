# Independent winning-account cash/share/NAV audit — 11 October 2026

Arithmetic audit passed on the frozen inputs. The same fixed configuration reproduces every result field and all curve, transaction and signal cells within $1e-07 absolute numerical tolerance. A separate standard-library accountant reconstructs orders directly from frozen signals, nominal vendor quotes and portfolio rules; recorded quantities and cash balances do not drive its calculations.

The $10,000 account starts on 2 June 2025 with no inherited holdings, remains in cash until the 30 June signal, first buys STX, PLTR, WDC, MU and AMD at 1 July 2025 opens, and ends on 2 June 2026 at $51,081.80757124. Net return is 410.8180757124% and maximum drawdown -17.9951960691% from 2025-11-10 to 2025-11-21.

There are **23 transactions**, comprising 11 buys and 12 sells, over 252 sessions and 12 monthly signals. Transaction counts of 24 in any external description would be incorrect for this ledger. Costs sum to $136.8615806732; dividends total $78.6400000000; ending cash is $7312.9278105011. Maximum reconciliation residual is $7.27595761418e-12. Every buy is whole shares and cash funded, every sell is limited to owned shares, all independently generated trades match source quotes, gross/cost/cash_after, and all daily cash, NAV, position counts and cumulative costs reconcile.

No corporate split or spinoff falls on a held position in this account. Historical/future vendor actions still enter nominal-unit reconstruction and are inventoried. This arithmetic result does not certify unobserved company actions, payable-date funding, vendor-adjustment economics, index membership or fundamental data quality. No source or deployed strategy was modified.

The previous narrative that higher costs alone invalidate the winning-year result needs precision: at 100 bps per side this same account returns **+401.8318237701% before terminal liquidation**. A hypothetical deduction of 100 bps against its ending stock mark reduces that to **+397.4549357941%**. At 20 bps it remains +409.9426981172% after the corresponding mechanical deduction. These deductions do not establish achievable next-session liquidation prices.

The archive SHA-256 matches `1315b523195777aea09edb40cf2c1534d81652886d7110f9dcb0c02ca3ab0af8`. All 1144 manifest-listed archive members pass SHA-256 verification; required workspace inputs also match. Six deliberate mutations (cash_after, opening quote, quantity, daily NAV, daily cash and execution date) are caught.

Files: `daily_reconciliation.csv` audits every session; `trade_checks.csv` details every order; `cash_events.csv` records funding/dividends/trade proceeds; `daily_holdings.csv` records every position; `daily_issuer_pnl.csv` independently attributes daily and cumulative net profit; `summary.json` records checks and source limitations. Retention and sizing remain research rules chosen on reused history, not a prospectively validated advantage.
