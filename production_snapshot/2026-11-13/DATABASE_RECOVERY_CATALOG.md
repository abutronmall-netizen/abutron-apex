# ABUTRON Database Recovery Catalog — 2026-11-13

This is **an index, not a database dump**. It contains no customer records or passwords. Database content is held in encrypted Restic snapshots on the authorized offsite repository; GitHub stores only this catalog and the software source snapshot.

## PostgreSQL — consistent logical dump archives

Production exporter ran `pg_dumpall --globals-only` plus a separate `pg_dump --format=custom --no-owner --no-acl` for every non-template database, including:
- `abutron_recovery_legacy_app_20261023`
- `abutron_recovery_legacy_platform_20261023`
- `abutron_v7_release_store`
- `postgres`

Validation: `pg_restore --list` passed for each logical dump. Remote readback of V7 dump and `restic check` passed for encrypted Restic snapshot **156e059c**, 2026-11-13.

## SQLite — online API backup copies

**70** database copies created from read-only connections, with SQLite `quick_check(1)` successful on both source and backup. Consistent SQLite copies located in `/run/abutron-db-online-20261113` are included in the supplemental encrypted backup.

| Original database path | Snapshot filename | Bytes | SHA-256 prefix |
|---|---|---:|---|
| `/var/lib/abutron-quant-first/forward-cost-shadow-v1.sqlite3` | `db-be9c53d66f16fa67a0a0.sqlite3` | 466944 | `3ac6c39c0a9c2d…` |
| `/var/lib/abutron-quant-first/entry-model-forward-v1.sqlite3` | `db-e5bb12b5ff2a55fba1bd.sqlite3` | 16384 | `ab6ca49ab3b32a…` |
| `/var/lib/abutron-quant-first/entry-model-causal-v2.sqlite3` | `db-78b316e7636d9bccf615.sqlite3` | 118784 | `ea1ee9455c6271…` |
| `/var/lib/abutron-quant-first/signal-outcomes/signal-outcomes.sqlite3` | `db-db708a5b6d207ea52a26.sqlite3` | 8192 | `2c25e8337ed8b5…` |
| `/var/lib/abutron-quant-first/tick-intelligence/quotes.sqlite3` | `db-29598886385e75d7c837.sqlite3` | 4431872 | `afd5bba7bace96…` |
| `/var/lib/abutron-quant-first/signal-attribution/decision-events.sqlite3` | `db-f41badf60e22f3c44a2d.sqlite3` | 90112 | `e49544e8a5e943…` |
| `/var/lib/abutron-quant-first/dual-broker/fp-immutable-native-candles.sqlite3` | `db-fba127822256868dda04.sqlite3` | 17190912 | `983aacbd118fdd…` |
| `/var/lib/abutron-quant-first/rdagent-qwen-discovery/verified-native-model-fills.sqlite3` | `db-9c131df25f12bfb21eec.sqlite3` | 16384 | `7c51a14ac8f5f7…` |
| `/var/lib/abutron-quant-first/rdagent-qwen-discovery/prospective.sqlite3` | `db-c6c82c70043c723eb926.sqlite3` | 1933312 | `64a5859e6b3d2d…` |
| `/var/lib/abutron-apex11-7593/account-bound-m5-journal.sqlite3` | `db-c29dfc9e7b458a902a77.sqlite3` | 14499840 | `a3d8f6bfdce7db…` |
| `/var/lib/apex/precision-history-ai-snapshot/closed-candles.sqlite3` | `db-7e24b99e646165bedd64.sqlite3` | 20533248 | `543f6517504b0a…` |
| `/var/lib/apex/precision-history/closed-candles.sqlite3` | `db-34c2d35425cdfc19bb79.sqlite3` | 20533248 | `c995845f8746ba…` |
| `/var/lib/apex/execution/intent_ledger.sqlite` | `db-42249b294c3c8e894157.sqlite3` | 40960 | `b3a620618038f7…` |
| `/var/lib/apex/demo-execution/attempts.sqlite` | `db-1b246449768d52adce1b.sqlite3` | 16384 | `dfce2967b359f6…` |
| `/var/lib/apex/demo-execution/v3-checkpoints/20261031T214712Z/attempts.before-v3.sqlite` | `db-8decbde60490141997b4.sqlite3` | 12288 | `90a29a567717d1…` |
| `/var/lib/apex/warehouse/deriv_broker_candles.sqlite` | `db-309e93312e2e5da898ce.sqlite3` | 9957376 | `74315c17bad989…` |
| `/var/lib/abutron-apex11-fp-0512/account-bound-m5-journal.sqlite3` | `db-079e0910e36c38512228.sqlite3` | 20480000 | `261827f72e7a66…` |
| `/var/lib/abutron-v4-broker-crm-supervisor-6207/six-account-observed-equity.sqlite3` | `db-2d087912344e143d4450.sqlite3` | 2957312 | `9ec866839fdb34…` |
| `/var/lib/abutron-apex11-6207/account-bound-m5-journal.sqlite3` | `db-e9623e64d7bd3231b834.sqlite3` | 15527936 | `d960f40c477284…` |
| `/var/lib/abutron-apex11-6207/v4-customer-risk-reservations.sqlite3` | `db-49ce08d7ef5b0c0ecb30.sqlite3` | 249856 | `0241317e6b552b…` |
| `/var/lib/abutron-apex11-fp-1636/account-bound-m5-journal.sqlite3` | `db-d66717af0420be3db1b0.sqlite3` | 21381120 | `06aafae98071d7…` |
| `/var/lib/abutron-native-quote-cost/authenticated-mt5-evidence.sqlite3` | `db-b1049d9fc646f2b3f625.sqlite3` | 218152960 | `6c0d52dc2b619f…` |
| `/var/lib/apex-broker-deal-evidence/verified_trades.sqlite3` | `db-6f65b8538816c1ceee21.sqlite3` | 53248 | `9f8282ab0ea701…` |
| `/var/lib/abutron-tick-factor-shadow/readonly-public-spot-snapshot.sqlite3` | `db-86285db815b51021b699.sqlite3` | 199892992 | `9458922a818cf7…` |
| `/var/lib/abutron-tick-factor-shadow/prospective-tick-aligned.sqlite3` | `db-70cea886254bea9315ff.sqlite3` | 5017600 | `48acce3b4a7156…` |
| `/var/lib/abutron-apex11-fp-2582/account-bound-m5-journal.sqlite3` | `db-964fff69518cc40fb1a3.sqlite3` | 1024000 | `93d5999064c52e…` |
| `/var/lib/apex-signup/accounts.sqlite3` | `db-38dc1f8f9500b6b085e1.sqlite3` | 2039808 | `c535789889b27d…` |
| `/var/lib/private/abutron-client-mt5-35b81a287b6a030f2f46ff426b135e6c/terminal-retired-1794380383956574704/llm-agent/data/sessions/sessions.db` | `db-3250da3a48a7f9715c00.sqlite3` | 90112 | `96440e2104604a…` |
| `/var/lib/private/abutron-public-spot-research/public-spot.sqlite3` | `db-cae21fd3e3dd5947c2b0.sqlite3` | 252047360 | `0212b41c2c97ac…` |
| `/var/lib/apex-smc-shadow/forward_outcomes.sqlite3` | `db-d0a3fa3c6d2b54a23f1f.sqlite3` | 262144 | `eea6fcb03ec4f7…` |
| `/var/lib/apex-smc-shadow/observations.sqlite3` | `db-877634a3deef27119bd0.sqlite3` | 5726208 | `87a1e84e7997db…` |
| `/var/lib/abutron-native-forward-cost/shadow-native-cost.sqlite3` | `db-7b569f539902164f8c5f.sqlite3` | 1523712 | `a90521b8e93d88…` |
| `/var/lib/abutron-fp-execution/order-router/order-journal.sqlite3` | `db-811b89a50511b0dfc93a.sqlite3` | 131072 | `5381cf74e25462…` |
| `/var/lib/abutron-fp-execution/1636/order-router/order-journal.sqlite3` | `db-1ebc777b7bc5a9652a5e.sqlite3` | 86016 | `22f3c9b55ccd26…` |
| `/var/lib/abutron-fp-execution/1636/reconciliation/broker-audit.sqlite3` | `db-1bdc4c40fa7b5ea36c34.sqlite3` | 704512 | `99ea2d04e66a92…` |
| `/var/lib/abutron-fp-execution/2582/order-router/order-journal.sqlite3` | `db-dfc689212b667202a05e.sqlite3` | 16384 | `03bc6791987ebc…` |
| `/var/lib/abutron-fp-execution/2582/reconciliation/broker-audit.sqlite3` | `db-4197476b49a8133c6cde.sqlite3` | 57344 | `4725c8ab360e2a…` |
| `/var/lib/abutron-fp-execution/1622/order-router/order-journal.sqlite3` | `db-e3622a83d83183a773ad.sqlite3` | 69632 | `887106da3d0201…` |
| `/var/lib/abutron-fp-execution/1622/reconciliation/broker-audit.sqlite3` | `db-2bc1c35450175e10ec41.sqlite3` | 569344 | `f627e4ee13c21c…` |
| `/var/lib/abutron-fp-execution/reconciliation/broker-audit.sqlite3` | `db-ad138f0883454720819f.sqlite3` | 2183168 | `2ed92b1ddeddff…` |
| `/var/lib/abutron-apex11-fp-1622/account-bound-m5-journal.sqlite3` | `db-21f9e8402d91de33c2be.sqlite3` | 11501568 | `587a49ca8b17c4…` |
| `/var/lib/apex-ai-smc-evidence/confirmation.sqlite3` | `db-b0e0ba04a9a52d0658af.sqlite3` | 1622016 | `3bb681bb6da4fc…` |
| `/var/lib/apex-ai-smc-evidence/demo-veto-results/first_decisions.sqlite3` | `db-0901876b077de2fc09f1.sqlite3` | 483328 | `63eb7319cd19bf…` |
| `/var/lib/apex-ai-smc-evidence/prospective/first_seen.sqlite3` | `db-989613f13461f74ecb31.sqlite3` | 630784 | `1cc6b2efed5ff2…` |
| `/var/lib/apex-client-feed/execution-ledger.sqlite3` | `db-09948f6683e890359669.sqlite3` | 196608 | `73cec5ff86a079…` |
| `/var/lib/abutron-v7-mt5-enrollment-gate/rate-limits.sqlite3` | `db-c2b46a6a1b2400785800.sqlite3` | 24576 | `3c9c7dbcc3078d…` |
| `/var/lib/abutron-apex11-9244/account-bound-m5-journal.sqlite3` | `db-1be2f927c328d71d8495.sqlite3` | 14823424 | `863373f02fb68a…` |
| `/opt/apex/runtime/recovery/agentictrading-seed-clean.db` | `db-5bb3066f1d33be9cce6b.sqlite3` | 688128 | `2dbdc033a56ee7…` |
| `/opt/apex/runtime/recovery/agentictrading-seed-before-restore-20261031.db` | `db-88a200d5cd98693efcbc.sqlite3` | 1183744 | `68ee92e4f2f27d…` |
| `/opt/apex/upstream/Open-Finance-Lab__AgenticTrading/dashboard/storage/data/backtest.db` | `db-57a06c14675fbcba3cab.sqlite3` | 688128 | `2dbdc033a56ee7…` |
| `/opt/apex/migration-staging-20261101/source-state/execution/intent_ledger.sqlite` | `db-ebff77ba6fe861aab4c2.sqlite3` | 40960 | `b3a620618038f7…` |
| `/opt/apex/migration-staging-20261101/source-state/demo-execution/attempts.sqlite` | `db-82cb7b373721ac36917e.sqlite3` | 28672 | `995a1e49e719c4…` |
| `/opt/apex/migration-staging-20261101/source-state/demo-execution/v3-checkpoints/20261031T214712Z/attempts.before-v3.sqlite` | `db-da93fc2670278446cfdc.sqlite3` | 12288 | `90a29a567717d1…` |
| `/opt/apex/migration-staging-20261101/source-state/warehouse/deriv_broker_candles.sqlite` | `db-26fedc76bef9c0abaf25.sqlite3` | 12140544 | `ff6a9957393283…` |
| `/opt/apex/migration-staging-20261101/runtime/recovery/agentictrading-seed-clean.db` | `db-b1ee9cc050e7e6469b04.sqlite3` | 688128 | `2dbdc033a56ee7…` |
| `/opt/apex/migration-staging-20261101/runtime/recovery/agentictrading-seed-before-restore-20261031.db` | `db-08424fdf6e63b79d92eb.sqlite3` | 1183744 | `68ee92e4f2f27d…` |
| `/opt/apex/apps/agentictrading/dashboard/storage/data/backtest.db` | `db-fcb3d1c2e6e534ad62ee.sqlite3` | 688128 | `2dbdc033a56ee7…` |
| `/home/apexmt5/bridge-runtime/apex_deriv_accounts.sqlite3` | `db-7edb8cb41e4c1e41001b.sqlite3` | 12288 | `84788bb6a54031…` |
| `/home/apexagent/.abutron-ai-history-snapshot-test/test.sqlite3` | `db-717e26318272e0fbf986.sqlite3` | 1867776 | `b0860097b98087…` |
| `/home/apexagent/.local/share/apex-lab/backtest.db` | `db-0498bfa95047281185da.sqlite3` | 1413120 | `d8dd5b2f0811ad…` |
| `/home/dcagent/abutron-recovery/monitoring/v9365_native_research_signals.sqlite` | `db-9c02b9d6f09c2072b8bb.sqlite3` | 16384 | `d7b8818dc29915…` |
| `/home/dcagent/abutron-recovery/monitoring/v9366_deriv12_native_research_signals.sqlite` | `db-4379ef9c38b51c25f212.sqlite3` | 16384 | `d7b8818dc29915…` |
| `/home/dcagent/abutron-recovery/staging/reconstruction/v4-20260926-isolated/data/abutron_decisions.db` | `db-70d09fb673571c2fe796.sqlite3` | 12288 | `54faf3a459b696…` |
| `/home/dcagent/abutron-recovery/staging/frontend-builds/recovery_demo/recovery_synthetic.sqlite` | `db-780d3018f939e6cf56b9.sqlite3` | 229376 | `66a854e3de8dac…` |
| `/home/dcagent/abutron-recovery/staging/frontend-builds/isolation/test_only.sqlite` | `db-f178cdf6caef8081f10e.sqlite3` | 229376 | `4bd4ff13dd3bd7…` |
| `/home/dcagent/abutron-recovery/staging/mt5-fleet-control-20261025/simulation_runs/7715bd10-71a5-4723-b0ff-4863aba3dd12/mt5-fleet-simulation/simulated_registry.sqlite3` | `db-f2183ff1b8a3cd7f4da6.sqlite3` | 28672 | `54f4609c1f02a6…` |
| `/home/dcagent/abutron-recovery/staging/mt5-fleet-control-20261025/simulation_runs/de82f535-61cc-46c2-aee9-164f17aadd57/mt5-fleet-simulation/simulated_registry.sqlite3` | `db-36331fff72bda0b97ced.sqlite3` | 28672 | `672352e5a1a5c3…` |
| `/home/dcagent/apex-mt5-diagnostic-stage/test.sqlite3` | `db-d4e8eea5d42ac359e1ce.sqlite3` | 413696 | `dd45bbe6a87b48…` |
| `/home/dcagent/apex-mt5-auth-staged/test.sqlite3` | `db-b8d1081c87ab48bea79d.sqlite3` | 413696 | `3c7819dab52238…` |
| `/home/dcagent/apex-worker-sandbox/accounts.sqlite3` | `db-90341af4901fe271b9af.sqlite3` | 397312 | `db79dad7e67429…` |

## Files ending in .db that are NOT SQLite

These were not converted to SQLite; preserve their original binary files through the primary raw-source backup.

| Original path | Treatment |
|---|---|
| `/opt/abutron-research/docker-data/volumes/metadata.db` | Non-SQLite format; preserve raw |
| `/opt/abutron-research/docker-data/buildkit/history_c8d.db` | Non-SQLite format; preserve raw |
| `/opt/abutron-research/docker-data/buildkit/cache.db` | Non-SQLite format; preserve raw |
| `/opt/abutron-research/docker-data/buildkit/containerd-overlayfs/metadata_v2.db` | Non-SQLite format; preserve raw |
| `/opt/abutron-research/docker-data/network/files/local-kv.db` | Non-SQLite format; preserve raw |

## Recovery warning

This index is not a restore certificate. The source PostgreSQL and SQLite dumps were validated structurally, but an independent full working environment restore has not been performed. Some running database states may change after the snapshot instant. Do not deploy these credentials or data to a public Git repository.
