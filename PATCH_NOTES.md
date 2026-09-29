# Paper Position Visibility UI Patch

## What changed
- Shows every current paper position directly inside the $10,000 shadow-portfolio card.
- Each position shows ticker, shares, average entry, current value, current P&L %, weight, entry rank and optimizer reason.
- Ticker links open the stock analysis.
- Adds a recent paper-trade journal immediately below the position cards.
- Expands the full paper ledger with P&L, portfolio weight, entry rank and reason.
- `/api/live` now carries the compact recent paper-trade list so the display remains live without a page reload.

No trading/optimizer logic was changed. This is a visibility/auditability patch only.
