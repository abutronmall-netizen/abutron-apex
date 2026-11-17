# FP Markets DEMO 0512 — V118 source baseline and XTIUSD investigation

**Status:** SOURCE IMPORT ONLY / INVESTIGATION. Not a repaired, compiled or deployed V119 build. See [P0 Issue #17](https://github.com/abutronmall-netizen/abutron-apex/issues/17).

These are byte-for-byte copies of the source assets from the staged host V118 release `/usr/local/lib/abutron-fp0512-issue21-v118/` as inspected on 2026-11-17. The running EX5 was **not** modified or uploaded. The two source files must remain adjacent for `#include "AdaptiveRiskProofV2.mqh"` resolution.

| Source asset | Production SHA-256 |
| --- | --- |
| `AbutronFPNativeOrderBridgeV101.mq5` | `235538c1c26612d2c493043a2dd844aa7f2c4dcdc37bba4783a6895ec8908f9c` |
| `AdaptiveRiskProofV2.mqh` | `fc9a921ccb57eef6f4786ed8d8a1eb53fe6f01cdcf857fc8990dc8fb84517117` |
| **Compiled V118 EX5** (not included) | `998e112c3682e503efe45ed870e3d662c1b7ccf2b4c69b121bc3d870cccdcacf` |

**Observed reproduction (live evidence, DEMO-only):** nonce-bound native request `APEX_FP_NATIVE_ADAPTIVE_ORDER_V2` for `XTIUSD SELL` was consumed once; authenticated receipt `BLOCKED / NATIVE_USD_STOP_CALCULATION_FAILED`, with zero order and deal IDs; durable ledger `BROKER_BLOCKED_NO_ACK`. The current broad error message wraps the multiple `return false` points in `NativeAdaptivePlan()` and does not prove a particular failure predicate. This is unrelated to the earlier prior-session ACK ledger recovery.

**Positive control:** authenticated `XAUUSD.r SELL` entry order `425481024`, deal `301748276`, had native SL `3859.09` and TP `3829.45`, and the ledger showed `OPEN_PROTECTED`. Do not extrapolate XAUUSD's success to oil.

**Repair boundaries:** preserve DEMO-only, current V118 single-consumer and nonce semantics, existing receipt schema, `OrderCheck`, broker-side protective SL/TP, 0.10% per-trade equity risk baseline (and its 15% execution-cost reserve), 20% portfolio ceiling, and LIVE OFF. Do not replay already blocked signals. Proposed follow-up: instrument exact fail reason without modifying authorization or trade behavior, verify native XTIUSD `CopyRates` and `OrderCalcProfit`/minimum-lot calculations, then fix **only** the demonstrably failing check. Compile/test a distinct V119 candidate and reconcile a new broker-native receipt before considering any release.

**Do not merge this baseline as a 'fix'.** It imports previously untracked production source for review; it contains no XTIUSD correction. The live installation is not updated by this PR.
