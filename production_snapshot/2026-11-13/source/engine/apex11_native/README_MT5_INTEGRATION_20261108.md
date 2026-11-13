# ABUTRON — APEX 1.1.0 Native MT5 Integration Package

**Checkpoint:** 8 November 2026. Built against the 12 user-exported production Python source files from `localhost` (ZIP 70,277 bytes), with source-file SHA-256s recorded in `native_interface/ORIGINAL_PRODUCTION_SOURCE_HASHES.json`.

## What was actually implemented

1. **FP partial feed → APEX native M5 parser**, `abutron_replacement/fp_partial_native.py`. Supports the existing verified `abutron.fpmarkets.native.partial.readonly.v1` and full `abutron.fpmarkets.native.candles.v1` schemas. Accepts only genuinely published, account-bound DEMO symbols and prices; does not force 13/13 symbols for an APEX signal. Fresh authenticated quotes, native mappings and actual closed candles are still required; no synthetic candles.
2. **Existing Deriv/FP broker feeds → APEX read-only multi-account inspector**, `abutron_replacement/native_integration_probe.py`. Queries only DEMO accounts and current native files. Produces per-account source/bar counts and, when a *measured* instrument manifest is supplied, isolated APEX 1.1.0 BUY/SELL/HOLD decisions. Excludes all LIVE accounts. No MT5 credentials are read and there are no order writes.
3. **APEX output → native protocol formatter**, `abutron_replacement/mt5_native_protocol.py`. Produces 12-field DEMO-only adaptive protocol payload bytes matching the *exported Python writer* formats, conditional on matching APEX decision and a completed account/broker risk review. **It does not publish those bytes or send an order**. Deriv uses the existing SHA-256 opening-time ledger identity. FP uses the existing FP ledger digest and requires confirmation of the exported legacy scanner's `m5_closed_bar` timestamp convention because the source scanner was not in this export.
4. **Production source drift check**, `scripts/verify_production_sources.py`. Reads and hashes the 12 existing Python production files against the export. Does not modify them.
5. **21 additional tests**, alongside the 108 existing tests, for the broker schemas, FP partial feed, DEMO-only packets, account binding, ledger IDs, LIVE exclusion, and no native order publication.

## Why this is not yet an automatic trading deployment

Exported source shows that the current *live* routers still require old scanner and TradingAgents outputs. Existing `apex_signal_native_router_v1.py` is not an order sender: it deliberately raises `NATIVE_ORDER_RECEIPT_RECONCILIATION_NOT_CERTIFIED` after its inspection stage. `apex_native_order_runtime.py` is the real Deriv native writer, with account-specific adaptive enablement, durable ledger, EA readiness, protection and reconciliation. `fp_signal_order_router_v1.py` is the FP native writer and is hard-coded to one FP DEMO connection. Neither writer currently accepts APEX 1.1.0 candidates directly. This integration package does **not** patch those production writers.

The **latest user-provided live reports** showed Deriv: 3/5 verified feeds, zero fresh candidates, zero authorized accounts, zero orders. FP: 0 complete feeds across six linked accounts, zero orders, all blocked. Both were still research/inspection modes. Their status may subsequently change; recheck before taking any action.

### Specific current integration blockers

- **Native EA validation/receipt mapping**: the 12 Python source files document the native EA protocol but do not include the running EX5 source, current binary attestation, broker ACK/deal/position proofs or tested replacement writer. Formatting a packet does **not** prove the EA accepts it. Keep the existing durable ledger, single-writer, no-retry-on-unknown behavior, and native `OrderCheck` / `OrderCalcProfit` checks. Do not hand-copy request files to MT5.
- **Deriv order runtime**: `apex_native_order_runtime.py` calls the legacy router's `plan()` again at dispatch, so an externally injected APEX candidate would be rejected. It requires a single-account adaptive allowlist. `customer_order_ledger.reserve()` additionally rejects M5 entries older than 240 s: this is an **existing** code rule, not one introduced by this package. The old runtime's `ensure_twenty_percent_nominal_equity_ceiling()` also includes `$52` fixed-stop assumptions even in adaptive code; review against 0.10% equity risk before any dispatch.
- **FP writer**: hard-coded connection `35b81a287b6a030f2f46ff426b135e6c`, hard-coded `FPMarketsSC-Demo`, scanner/TradingAgents review requirement, and a separate FP ledger. FP `closed_bar` timestamp semantics cannot be independently established from this export (scanner source absent); the preview protocol demands the exact timestamp basis instead of guessing a broker receipt key. The collector was also blocked by native quote/clock freshness in the prior inspection; partial source reading cannot create missing quotes.
- **Broker instrument metadata**: the attached source exports have OHLC prices, some FP mapping/min-lot/contract fields, but **not a fully measured current stop/tick-value/commission/slippage manifest** for every instrument. APEX 1.1.0 requires instrument metadata. Do not use `examples/manifest_EXAMPLE_NOT_REAL_COSTS.json` for production execution.
- **Client controls**: `desired_enabled=0` or `effective_enabled=0` are genuine client-trading OFF controls, not extra strategy research gates. No automatic execution should override those controls or any LIVE account state.

## Safe host-side verification (NO trading)

From root SSH, after extracting this ZIP in an isolated directory and using the already-installed clean APEX virtual environment:

```bash
cd /opt/abutron-apex11-staging/native-integration-20261108/abutron_apex11_USER_DIRECTED_NO_EXTRA_GATES_20261108
/opt/abutron-apex11-staging/clean-20261108/venv/bin/python -m pytest -q -p no:cacheprovider
python3 scripts/verify_production_sources.py
/opt/abutron-apex11-staging/clean-20261108/venv/bin/python -m abutron_replacement.native_integration_probe
```

The inspector without `--manifest` checks broker DEMO source files and reports missing measured metadata; it does not fabricate APEX signals. The inspector may correctly report stale/absent FP exports on a market-closed Sunday.

**Do not:** `systemctl enable` any new order writer, invoke original `--dispatch`, change client switches, turn on an EA's native order input, change `LIVE` services, or copy the protocol preview into `MQL5/Files` as part of this staging command.

## Next actual cutover engineering

Replace the production Deriv `router.plan` and FP `match_signals` entry source with trusted account-bound APEX candidates, preserving each broker's native writer/exposure/receipt logic. Repair Deriv's adaptive risk proof, generalize FP's single-account binding, and fix the FP source clock/quote freshness. Then demonstrate per-broker DEMO broker-acknowledged entry, SL/TP protection, journal reconciliation, and automatic client ON/OFF behavior before enabling timers. Disable legacy decision timers only after the new dispatch path has real proof and rollback is ready. No extra research promotion thresholds or arbitrary waiting period.

## Backup state

The prechange encrypted offsite Restic backup initiated at `20261108T003004Z` on `localhost` completed with **repository integrity check passed and remote DB readback passed** in the earlier direct inspection. This package does not touch that backup, roll it back or assert full bare-metal restore has been tested.
