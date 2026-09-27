# V1 Requirements Matrix

## Dashboard / portfolio
- [x] Private-login capability via environment variables
- [x] Current positions — manual entry/edit/delete
- [x] Screenshot import — server vision when configured
- [x] Screenshot import — free browser OCR fallback
- [x] Confirmation/edit step before imported holdings are saved
- [x] Trade ledger
- [x] Cash and strategic reserve
- [x] Portfolio reallocation/deployment proposals
- [x] Manual symbol-analysis field with source/recommendation note

## Radar / decisions
- [x] Cross-sector broad candidate discovery
- [x] Continuous background loop during regular US session while host is awake
- [x] Existing positions get priority monitoring
- [x] Deterministic score /100
- [x] Analyst score /100 when data exists
- [x] Explainable AI/context score /100
- [x] Strong-fundamental gate for Explosive Runner
- [x] News sentiment in every analysis
- [x] News materiality
- [x] Source credibility heuristic
- [x] “Priced-in” recency heuristic, clearly labeled heuristic
- [x] Material bearish-news override
- [x] Sector momentum component when sector benchmark is available
- [x] Buy zone
- [x] Better-buy zone
- [x] Breakout-buy level
- [x] Do-not-chase level
- [x] Stop / thesis invalidation
- [x] Modeled target and risk/reward
- [x] New-position BUY NOW / WAIT MORE / BREAKOUT BUY / DON'T CHASE / AVOID / WATCH
- [x] Existing-position ADD / HOLD / HOLD-DON'T-ADD / TAKE PARTIAL PROFIT / REDUCE / EXIT
- [x] Analyst vs AI expected-yield display
- [x] Analyst vs deterministic vs AI holding-period display
- [x] AI score adjustments explained
- [x] Risks / contrary evidence shown
- [x] Conditions that would change the AI score shown

## Alerts / history
- [x] Buy-level alerts
- [x] WAIT MORE alert when buy zone is reached but evidence deteriorates
- [x] Existing-position profit/reduction/exit alerts
- [x] Alert deduplication if action is unchanged
- [x] Analysis snapshots persisted
- [x] Radar candidate state persisted
- [x] Live dashboard polling without page refresh

## Deliberately deferred beyond V1
- [ ] IBKR read synchronization
- [ ] IBKR approve-to-execute orders
- [ ] Automated execution
- [ ] Paid/exchange-grade real-time market feed
- [ ] Exhaustive full-US-universe tick scanner
- [ ] Dedicated production news feed
- [ ] Exchange holiday/early-close calendar
- [ ] Push notifications outside the website
- [ ] Programmatic eToro signal integration
