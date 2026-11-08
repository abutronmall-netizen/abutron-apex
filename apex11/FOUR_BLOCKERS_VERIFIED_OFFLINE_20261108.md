# Historical production verification — updated after user-requested gate removals

Archived read-only production findings from 8 November 2026 (no fresh server access for this revision):

- Deriv: protected MT5 M5 live snapshot was 100 bars per symbol; separate broker-attributed CopyRates research archive had 60,000 M5 bars per V10, V25, V50, V75 and V100 instrument and one gap per series. **There is no longer an APEX replacement 300-bar hard minimum.** The archive remains suitable for offline research, not automatic evidence of live broker execution.
- FP Markets: two recent exports had quote timestamps approximately 24 hours behind the collector, and the read-only collector correctly marked them stale. This is not simply a 2-hour timezone-offset problem. Fixing the actual broker source still requires genuinely fresh market data.
- Deriv and FP current production routers required legacy scanner and TradingAgents approvals, with an additional handover field in Deriv. **The new offline candidate evaluator no longer depends on those requirements, but the production routers have not been changed.**
- Historical research costs: short authenticated native spread samples and broker commission estimates were available, but complete time-aligned historical spreads and actual slippage distributions were not established. The new cost evaluator is descriptive only, without an added statistical promotion gate.

The source code in this package has undergone a local test revision for the eight explicit removals; no claim of profitable trading or a production cutover is made.
