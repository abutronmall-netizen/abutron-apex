# FP Markets DEMO history clock — source-only corrective contract (2026-11-08)

**Status:** offline module and tests only. Nothing deployed, no live MT5 calls, no broker positions or order settings modified. LIVE remains disabled.

## Forensic evidence on localhost

- FP MQL5 source recovered: /var/backups/abutron-fp-native-bridge-prestage-20261104T182821Z/files/home/dcagent/abutron-fp-history-staging-20261104/AbutronFPAccountHistoryV100.mq5
- MQL5 V100 lines 50–52 use datetime now=TimeCurrent(); from=now-90*86400; HistorySelect(from,now+60). OnTimer every 60 seconds.
- Native export header lines 17/18 are broker-server epoch seconds from and now+60; line 7 is TimeTradeServer()-TimeGMT(), independently validated as 7200 by the Python collector. Line 6 generation time is UTC TimeGMT().
- Original production collector: /opt/apex-client-mt5/fpmarkets-history/fp_native_history_collect.py checks end>=time.time()-86400 WITHOUT first converting broker-server end to UTC. A file can be just seconds old while its MQL5 TimeCurrent() was frozen at Friday's last quote.
- Observed Sunday 2026-11-08: raw broker-server end represented as 2026-11-07 00:00:59 *server time* (+02), equivalently Friday 2026-11-06 22:00:59 UTC; full window=90d+60s; native export tag matched.
- MQL5 compiled indicator matched installed runtime SHA256 5f1996c4a06b8ad29cf4dc615bebce356c3ba3d6e5e25d7b28abb19a966f5683.

## Safe integration into existing Python collector

The production module is not yet imported to this GitHub repository. **Do not blindly deploy this helper as a complete replacement** for fp_native_history_collect.py, which includes authoritative account/nonce binding and positions/deal evidence validation not reproduced here.

After verifying a full offsite Restic backup and testing rollback:

1. Preserve existing broker_account, worker_proof, file read, account binding, generation-stamp, 7200 offset, USD, totals and final sentinel checks.
2. At the existing combined FP_HISTORY_SELECTION_INVALID check, convert the MQL5 broker-server window to UTC only for *cross-clock comparisons*: begin_utc=begin-offset, end_utc=end-offset. The native HistorySelect broker-server begin/end must remain unchanged.
3. Call require_fresh_fp_history_window(lines[:20], observed_utc=int(now)) **after** native account/offset/identity checks and before publishing an execution-eligible report. This throws FP_HISTORY_LAST_QUOTE_STALE if the last actual quote is too old. inspect_native_fp_history_window returns a safe monitoring diagnosis such as MARKET_CLOSED_OR_QUOTES_STALE, *not* BROKER_DISCONNECTED, only when the account's separate heartbeat remains valid. Weekend is a clue, not verified market-open status.
4. Keep live execution blocked if native M5 bars, OrderCheck, risk, broker reconciliation or account activation are missing. Neither this helper nor a recent report can authorize an order.
5. Test with truly fresh, broker-authenticated quotes after FP market reopening; validate MQL5 attachment identity, independent broker server UTC offset, complete history count and positions/deal reconciliation before relaxing any operational incident status. Do not touch file mtimes or fabricate TimeCurrent()/TimeTradeServer() values to pass a check.

## No claim of milestone completion

This change covers the diagnosed FP history-window sub-blocker only. FP native candle completeness, native order writer, customer aggregate risk and real authenticated broker demo order lifecycle remain open (Milestone B). Deriv 6207 broker-confirmed Milestone A and platform/security Milestone C remain independently gated.
