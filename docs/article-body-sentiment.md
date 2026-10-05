# Article-body author sentiment

The canonical scanner enriches up to 15 relevant, recent news items with cached article assessments before `score_bundle`. Market scans and requests enqueue keys in `news_article_assessments`; they never wait for publisher HTTP. The default worker count is one (maximum two).

Complete article bodies are checked for explicit, current, company-specific author recommendations. Questions, conditional choices, attributed quotes, competing-stock choices and ambiguous bodies stay unassessed. This is a conservative rule engine, not unrestricted semantic sentiment analysis. A clear bullish recommendation adds one opinion signal through the existing publisher weight and 1.5 news-point multiplier; bearish/mixed recommendations retain adverse evidence. Duplicate stories contribute once. Author opinions do not create factual catalysts, material-negative overrides or thesis-breaking events. The 7.5 neutral baseline, news maximum of 15 and label thresholds remain unchanged.

The UI distinguishes article opinion from headline events, shows a bounded evidence excerpt and explains pending/unassessed/unavailable cases. Completed article assessments invalidate canonical candidate/API caches. Cache identity includes ticker, normalized URL and classifier version; successful entries refresh after 24 hours, failed/unassessed entries after six hours when requested again. Expired processing leases recover after restart. Cache entries unused for 30 days are removed.

## Resource controls

- One default worker; configurable hard maximum two.
- Durable pending queue capped at 3,000, with holdings prioritized and no in-memory HTML queue.
- Public HTTPS URLs and redirects only, connect/read timeouts and a 25-second streaming deadline.
- Separate 1 MiB wire and decompressed limits; 8 KiB chunks; 30,000 text characters.
- Stop fetching once a recognized complete article body is extracted, allowing large trailing advertising markup.
- Persist at most 4 KiB assessment metadata; no HTML or full article text stored.
- Pause new article work at 350 MiB whole-service cgroup usage, resume below 300 MiB. In development use process RSS.

## Validation (2026-10-05)

58 new article tests pass in GitHub CI, including six ticker families, bullish/bearish recommendations, competing-stock choices, negation, conditional/quoted language, duplicate opinion points, no manufactured catalysts or thesis sell, HTML/body selection, compression bombs, byte/depth/deadline limits, URL redirects, queue cap, retry, stale lease recovery and cache invalidation. The whole CI suite reports 391 passing and 22 failing entries. The same 22 failing entries occur on the deployed v8 baseline (333 passing), with no added failures. Production Python 3.14 imports, Python compilation and dashboard JavaScript syntax checks pass.

The previously retrieved original CREDO comparison article yields a positive author opinion from its explicit choice, with zero fresh factual catalysts. This is source validation, not a ticker-specific override.

A repeated replay of the real scanner and new database-backed worker completed six cycles, 48 deep analyses and 200 prefilter checks per cycle, using a 5,755-symbol synthetic universe and four full SEC fixture datasets reparsed on each analysis. It processed 2,160 near-1-MiB HTML pages with approximately 28,000-character bodies; alternating cycles exercised completed cache hits. There were no scan errors. Sampled peak RSS was 129.91 MiB; cycle endpoints were 123.42, 124.18, 126.43, 126.43, 128.93 and 128.62 MiB. Total duration was 31.73 seconds. Publisher HTTP was replayed offline, the database was SQLite, and external AI/government HTTP/PDF work was excluded. These are measured local resource results, not a guarantee about live publishers or production memory.

Trading eligibility, sizing, allocation, targets/stops, canonical paper account and trial clock are unchanged. The implementation is generic across tickers. It does not guarantee that every article has a determinable sentiment or that investment returns improve.
