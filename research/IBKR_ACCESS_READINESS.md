# IBKR access and historical pilot readiness

**Externally blocked: no authorized IBKR interface is available in Codex.**
Checked10 October2026. The exposed tool catalog has no IBKR connector/search
interface; environment binding names include noIBKR/TWS/Gateway/Client Portal
requirement. The saved configuration has only the existingEODHD market-data
binding. None of the standard local ports7496,7497,4001,4002,5000 listens;
ibapi/ib_insync/ib_async are not installed. No remote host/session is configured.
These checks do not establish that the user's external IBKR account lacks
permissions; they establish that this Codex task cannot access it.

No login, market-data request, contract lookup, subscription or trade was
performed. A ChatGPT connector does not automatically supply a Codex interface.
The earlier CSV is metadata: Korea1216 daily bars from2021-10-12 and Taiwan842
bars from2023-04-25 through2026-10-08, with six contract IDs. It contains no
OHLC/TR bars, no actual subscription permissions or dated contract histories.
Taiwan's observed range does not provide253 prelaunch sessions forOctober2023.

To unblock: supply a user-authorized read-only historical-data interface/relay,
or an authorizedTWS/Gateway endpoint and runtime session with market-data
entitlements documented for the required venues. Configure secure credentials
in environment settings; do not paste values into chat or files. An entitled
export with contract metadata is also sufficient for independent data work.
Network publication alone cannot create broker access or entitlements.

Once available, first verify read-only authorization and cost-free existing
entitlement. Pilot at most three mapped contracts:SPY plus directSamsung
Electronics andTSMC. Query contract details first; preserveconId,localSymbol,
secType,exchange,primaryExchange,currency,ISIN and validity evidence. Compare
ADRs and ordinary lines explicitly. Request small daily histories with
completed-session boundaries and report earliest/latest rows, adjustment basis,
gaps, permission errors and truncated/expired-contract history. Only extend
the pilot range after verifying rights and pacing. Never invoke order APIs.

Use a sequential conservative pilot (one historical request in flight; at
least20seconds between historical starts; no identical request inside15seconds;
no burst/retries). These are conservative proposed limits, not a verified
account-specific allowance. The commonly cited small-bar pacing rules cannot
be assumed to apply identically to one-day bars orClient Portal. Official
`interactivebrokers.github.io/tws-api/historical_limitations.html` retrieval
failed with proxy403; confirm current endpoint-specific limits before a pilot.
No blocking pacing sleeps were run because no requests were authorized.

The saved draft adds that documentation host and preserves all prior settings;
review/save and publication activate it. Actual broker host/session/entitlement
is the remaining independent prerequisite. Ignored access audit records zero
historical and contract requests. Six admission/quota regressions passed.
