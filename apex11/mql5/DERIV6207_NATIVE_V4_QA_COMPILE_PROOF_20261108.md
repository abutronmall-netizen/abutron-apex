# Deriv 6207 APEX 1.1.0 — verified isolated MQL5 native V4 compile

**Checkpoint: 2026-11-08 06:35 UTC / 08:35 SAST. This is a QA compile, NOT a production EA deployment or Milestone A acceptance.**

## Exact trusted inputs

- Owner-verified native MQL5 original include: `AdaptiveRiskProofV2.mqh` SHA256 `e2e4e01ef5e96f888f687a45e21de83cfc78b419787a0c3667d96914d1cc3c44`. Three original backup copies had identical bytes; the root-owned, restricted group-readable handoff was verified accessible to `abutrongha`.
- Current APEX native V4 candidate: `apex11/mql5/AbutronApexExistingDerivV4_6207.mq5`, Git blob `319c68d825b235ffaaa1eb2b7bdf5b82d35aa838`. This is the corrected source produced from the previously independently verified 681-line November 7 adaptive EA source. PR #13 merged to APEX main in commit `d497f449d9d69399996cfe9ae1f564dbb8f333c0`.
- Both APEX offline source and integrated CI checks passed on PR #13 head `66bea78b46d61ba14c53de30c1b9203a3c25a17d`.

## Compiler evidence

1. Non-root production runner verified exact include SHA and Git source blob, then uploaded only those files to a 1-day private GitHub Actions artifact. No broker login, terminal configurations or keys were included.
2. A disposable GitHub-hosted Windows runner downloaded the official MetaQuotes MT5 installer and verified its Windows Authenticode signer. Installer SHA256 `a879492dd9d7b168d0538edd1c0dc5604ca43dc0951825b3501818e8b18f4c93`. Installed MetaEditor64 executable signature also validated; SHA256 `ce4393bcbf3f73dfd8f5e50c42db71e5179b6a96e59e655ba87ffd1d301b6248`.
3. First native Windows QA run `42455127436` (on previous source Git blob b2ba334...) logged **0 MQL5 errors, 2 operator-precedence warnings at lines 528–529**. The two warnings were fixed by explicit `sideIsDirectional` boolean, preserving BUY/SELL rejection semantics.
4. Final Windows run `42455355502` succeeded. Actual MetaEditor compilation log reports **`Result: 0 errors, 0 warnings, 1440 ms elapsed, cpu='X64 Regular'`**. Both jobs (source verification and Windows compile) passed. MetaEditor launcher returned code 1, but EX5 file presence, log result and digest were independently checked by QA workflow.
5. Produced EX5: SHA256 **`5092b1b395ff91539f4d9952f89bc6976211ff43d4c7794caf7a76526a1d2ec9`**, **54,342 bytes**. QA artifact `abutron6207-v4-unapproved-qa-binary` in [Actions run 42455355502](https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42455355502), private artifact ID `13607029408`, expires **2026-11-09 06:35:52 UTC**. Its short retention does not affect durable source code or the reproducible build record.

## Production safeguards and remaining Milestone A gate

- **No compiled QA EX5 was copied into any live 6207 MT5 terminal.** No live EA binary, chart, service, broker order, customer effective switch, V3 dispatcher or LIVE trading setting was modified.
- The V4 source's `V4RevisionAuthorized` native function explicitly **returns false**; it still lacks an independently authenticated root-owned CRM activation lease and race-free client OFF vs in-flight order fence. Native V4 input defaults OFF; old V2/V3 order consumption is disabled in this candidate. Therefore the compiled candidate is intentionally non-executable for broker orders.
- Before even a DEMO cutover: complete and verify native root-owned activation-revision/lease supervisor and secure EA handshake, authoritatively reconcile unknown orders/positions, back up installed EA and chart configuration, verify 6207 independent broker authentication, and prove exact customer risk limits (0.10% trade, 2% aggregate, 3% day, persistent 20% peak drawdown).
- Then use only a **fresh qualified APEX M5** signal to perform at most one controlled broker-confirmed Deriv 6207 DEMO order, attest broker order/deal/position IDs and broker-set SL/TP, and test customer OFF fencing. Do not force orders or bypass risk to claim acceptance.
- **Milestone A status: native source + original include recovered, zero-warning EX5 QA build VERIFIED; live writer/EA activation guardian and broker DEMO order acceptance NOT VERIFIED. LIVE remains OFF.**

## Related evidence

- [Milestone A Issue #4](https://github.com/abutronmall-netizen/abutron-apex/issues/4)
- [Source repair PR #13](https://github.com/abutronmall-netizen/abutron-apex/pull/13)
- [Real MetaEditor Windows QA run](https://github.com/abutronmall-netizen/abutron-ops/actions/runs/42455355502)
