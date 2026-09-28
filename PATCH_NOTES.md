# Better Buy Decision Patch

Fixes overly sensitive WAIT behavior inside the Better Buy zone.

## What changed
- Better Buy no longer treats a single mild technical weakness signal as a falling-knife condition.
- WAIT MORE in Better Buy now requires converging weakness (multiple negative technical signals) or material bearish news plus weak momentum.
- Mild residual weakness can produce CONSIDER STARTER BUY.
- Stable Better Buy setups can produce CONSIDER BUYING NOW or BUY NOW depending on score.
- Reasons now include RSI, 20-day change, and price-vs-EMA20 context.

## Regression
45 passed / 0 failed.
