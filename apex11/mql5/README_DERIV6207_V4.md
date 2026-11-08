# ABUTRON APEX 1.1.0 — native Deriv DEMO 6207 V4 EA candidate

**Status: offline source candidate, NOT a production MT5 binary or execution authorization.**

## Proven source origin

Owner root established original 681-line EA `/var/backups/abutron-five-volatility-prechange-20261107T105218Z/adaptive_bridge.mq5` with SHA256 `dfc436a42d5210e93f51652e1ac95c65820a3b906cf2629808f9c93850998bc3`. A root-owned read-only group copy was made at `/var/lib/abutron-apex11-source-handoff/adaptive_bridge.mq5`; a non-root GitHub Actions check (Ops run 42452227059) validated the exact hash and source (681 lines) without widening production sudo.

This directory contains `AbutronApexExistingDerivV4_6207.mq5`, a new candidate derived from those exact bytes. It preserves the original adaptive risk math and single-attempt broker send logic in place, adding a distinct V4 parser and preventing the old router from authorizing orders.

## Native V4 contract

- Native file path: `MQL5/Files/ABUTRON/ABUTRON_APEX_V4.req`; original legacy V2/V3 path is not consumed by this upgraded EA.
- Python writes **13 ASCII CRLF-delimited lines** (MetaQuotes `FileReadString(FILE_TXT)` expects CRLF):
  1. APEX_NATIVE_ACCOUNT_BOUND_ORDER_V4
  2. Worker nonce (32 lowercase hexadecimal)
  3. Canonical signal ID (64 lowercase hexadecimal)
  4. Broker account login (Deriv DEMO ending 6207)
  5. Deriv-Demo
  6. V10/V25/V50/V75/V100 approved broker symbol
  7. BUY or SELL
  8. Explicit reserved native lot volume
  9. Explicit native stop-loss price
  10. Explicit native take-profit price
  11. Customer account activation revision
  12. Unix UTC expiration (no more than 12 seconds)
  13. SEND_DEMO_ONLY
- EA checks 13-field format, nonce/login/server and demo identity, unique archive-before-send, exact native lot step, broker tick, margin, stop/freeze distances, protected RR and broker `OrderCalcProfit`/`OrderCheck`, original Option C evidence, and a single `OrderSend` attempt with UNKNOWN on uncertainty.
- Legacy V2/V3 order consumption and capability **remain hard disabled** in the V4-only candidate, even if a local MT5 user changes original input toggles. Current file-specific V4 ON input defaults OFF.
- `V4RevisionAuthorized` **always returns FALSE** until an independently authenticated, root-owned, fail-closed native activation supervisor implements atomic OFF-vs-in-flight fencing. A local ON boolean or EA-owned marker cannot establish the root authority. **No V4-ready capability is emitted.** This prevents new orders from passing when the independent supervisor does not exist.
- The existing Python V4 file port, account risk reservations and receipt guards remain separate and cannot substitute for root native verification.

## Explicit acceptance gates still outstanding

1. Recover **`AdaptiveRiskProofV2.mqh`**, the original EA include dependency, from the verified `ABUTRON_OptionC_Adaptive_Cutover_Source.zip` or protected MT5 terminal/backup files. No include byte hash has been independently matched yet.
2. Compile **in an isolated QA MT5 Wine prefix**, never directly in the customer 6207 terminal. The host has Wine and `/opt/abutron/client-mt5-template-v2/MetaEditor64.exe` (read-only discovery, Ops run 42452540152), but **native compile has not been performed**.
3. Implement the root-owned CRM activation supervisor and EA-authorized live revision/lease proof. OFF acknowledgments must wait for or safely fence outstanding unknown native requests; no writable file/boolean shortcut.
4. Verify actual chart-attached installed EA and EX5 digest; back up live chart/source/EX5/config and prepare rollback; source hash alone does not establish compiled binary provenance.
5. Validate full Deriv 6207 DEMO authenticated broker M5 feed, risk 0.10% trade / 2% aggregate / 3% day / 20% peak drawdown, exactly one eligible fresh APEX decision, native broker OrderCheck and one protected DEMO fill, positions/deals/SL/TP independent reconciliation and account OFF interrupt test.
6. LIVE remains OFF; do not enable old native order timer or fabricate a broker receipt.

**Do not claim Milestone A complete solely because GitHub offline tests pass or a source file is staged.**

## References

- MetaQuotes [FileReadString](https://www.mql5.com/en/docs/files/filereadstring): CRLF-separated `FILE_TXT` records
- MetaQuotes [FileMove](https://www.mql5.com/en/docs/files/filemove): no overwrite without `FILE_REWRITE`
- MetaQuotes [MetaEditor command-line compilation](https://www.metatrader5.com/en/metaeditor/help/beginning/integration_ide)
