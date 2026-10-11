# Monitoring, reconciliation and incident runbook

These are requirements for a future isolated service, not scheduled jobs installed by this change. G0 is offline. No new heartbeat automation, live service probe, deployment or trading schedule is started here.

## Operational monitoring

Use a verified NYSE calendar and `America/New_York` for market schedules, UTC for stored events, and Europe/Stockholm for user-facing dates. Do not use fixed UTC market-close times across DST. A monitor is useful only if it has an owner, deadline and tested delivery path. Proposed recipients are the user/release owner; connecting an external messaging service requires separate authorization.

| Signal / cadence | Target and escalation | Automatic response |
| --- | --- | --- |
| Worker heartbeat every 60 seconds during an active run | Warn after 2 missing heartbeats; critical after 5; staffed release owner while run active | Stop progression; expire execution lease |
| Price/calendar snapshot after each completed session | Exact latest session, completed close, no unknown calendar/action; expected snapshot within 30 minutes after close (operational target, not a grace-period data inclusion rule) | Hold stale/gap-dependent decisions |
| SEC collection checkpoints daily and prior-day seal on signal eve | Complete accession set for required periods; original source availability confirmed; observation log retained; detect amended/corrected source hashes | Reseal before signal only; after cutoff append correction and hold if material |
| Universe/identity changes daily; monthly all-member coverage | 100% member dispositions and verified effective intervals; unresolved critical identity count =0 | Whole-cycle hold |
| Run deadline at month-end / approved next-open window | Signal/QA completed before declared execution plan deadline; pending dependency alert immediately, never quietly skip | Mark missed window; no catch-up |
| Reconciliation daily and before every capability | Zero unknown fills; exact shares; cash/basis/NAV residual ≤$0.01; independent price/action status complete | Disable capability and open incident |
| Ledger/checkpoint on every append; full chain daily | Valid contiguous chain, stable event keys, external root match, durable storage/WORM healthy | Quarantine immediately |
| Duplicate-key/concurrent-owner attempts continuously | Zero conflicting keys/leases; identical retries are expected and counted separately | Reject conflict; alert on repeated failures |
| API errors/rate limit/dead-letter per acquisition run | At most 3 bounded attempts; circuit breaker after repeat source failure; queue oldest age and cutoff readiness visible | Stop source job; hold run; preserve attempts |
| Authorization denials/certificate expiry/revocations continuously | Every denial reason visible; denied capabilities never turn into fills; unused nonce/plan/QA hash consistency | Fail closed |
| Storage/backup/restore daily health; monthly restore drill | Signed off-host checkpoint and verified restore; proposed RPO 0 for committed trade intents/events, RTO ≤4 hours for read/reconciliation recovery | No purchases until all events recovered and reconciled |
| Drift weekly and each release | Build/source manifest, permission and account/storage endpoint checks match approved release | Revoke release on drift |
| Trial performance after daily reconciliation | USD NAV/exposure/turnover/costs, matched SPY, drawdown and missed/held cycles; no trading decisions from performance alerts | Informational; no strategy adjustment |

Monitor acquisition latency, snapshot coverage, QA failures by reason, pending certificate age, retries, processing duration, dead-letter age, ledger sequence/head hash and reconciliation residual separately. Health green cannot substitute for QA. Sustained service outage causes visible holds; keep existing paper service untouched.

At a monthly release review disclose universe/fact/action gaps, data corrections, operational opportunity losses, execution price deviations and differences between frozen ex-date model and economic cash. Retain the original and corrected views. Do not attribute outcomes to a full GEM trial when purchases were held for data reasons.

## Reconciliation equations

Independent replay from event history, not the simulator's aggregate summary:

* Shares = starting shares + buys − sells, transformed by proved corporate actions.
* Cash = starting cash − buy notional − buy costs + sell notional − sell costs + distributions + explicit external flows. Receivables are separate in the economic view.
* Basis allocates cost inclusive of entry charges, removes pro rata sold basis, and tracks split/spinoff basis events independently.
* NAV = cash + sum(shares × independently obtained exact-date nominal close); economic receivables are added only in the clearly labeled economic view.
* Ending NAV − starting capital − external flows = realized net P&L + unrealized P&L + distributions under the declared view. No residual plugs.

Missing marks are not forward-filled into a certified NAV. Preserve a provisional stale-mark view if useful, with a hold and stale count. Unknown order acknowledgement, action or dividend entitlement blocks further purchases until reconciled.

## Incident response

Severity 0: unauthorized/duplicate order event, wrong account/environment, rule/future-data leak, corrupt/rolled-back ledger, impossible cash/shares. Immediate deterministic disable/revoke; critical user alert through an approved channel; preserve evidence. Target acknowledgement ≤15 minutes when staffed; if no operator is available, remain disabled indefinitely.

Severity 1: missing competing security, ambiguous SEC time/units, unreconciled action/fill, stale snapshot/QA, missed execution deadline. Hold the affected run/account, notify release owner, target triage within one business day. Severity 2: non-critical report formatting/latency with complete evidence; queue for review. No severity can bypass a hard gate.

1. Activate the separate GEM kill switch and revoke authorization generation. Verify **GEM** namespace/account only; never reset or close existing deployed positions.
2. Record incident ID, first detection, last trusted checkpoint, current code/plan/QA/release/event hashes, raw evidence and affected run/cases. Preserve denied attempts as well as any intent/ack/fill.
3. Stop new intents. For an ambiguous simulator response, query existing key/state read-only and reconcile before retrying. Never issue a replacement order with a fresh ID.
4. Diagnose whether the cause is data, code, credentials, calendar, source correction, storage or concurrent ownership. Compare to trusted off-host snapshot. Do not edit a ledger, rewrite decisions or fill missing values from later facts.
5. Repair through reviewed code or compensating events; reproduce the failure offline; independent QA verifies the fix. A changed release digest requires fresh signoff under G4.
6. Restore only to an isolated read-only namespace; verify chain against external checkpoint, rebuild projections and independently reconcile all committed events. Missing durable intents means recovery is incomplete and purchases remain blocked.
7. Publish root cause, chronology, financial/decision impact, affected evidence, corrective controls and outstanding uncertainties. User/release owner explicitly clears the incident after independent QA; a worker never auto-clears it.

Rollback means disable/revoke and restore a previously reviewed read-only build. It does not undo actual historical simulated observations or erase losses. A missed GEM cycle is recorded; do not quietly purchase the prior basket later.

## B research incident handling

If a certificate is wrong, append a revocation linked to the old decision and mark all dependent cases/impact outputs stale. Keep original facts and rankings. Re-review shared accessions across all affected dates. No B correction can trigger an A purchase or change a previously sealed forward decision.
