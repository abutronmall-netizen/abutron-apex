# ABUTRON APEX 1.1.0

**Status: source imported and isolated components under draft review. NOT production-authorized. No LIVE trading.**

## Review branches and acceptance evidence

| Workstream | Link | Code status | Broker/platform acceptance |
|---|---|---|---|
| APEX source import | [Draft PR #2](https://github.com/abutronmall-netizen/abutron-apex/pull/2) | 97 original files, 108 baseline offline tests | Not deployed |
| Dual-layer DEMO risk | [Draft PR #1](https://github.com/abutronmall-netizen/abutron-apex/pull/1) | 47 isolated tests, risk reservations | No broker-native proof |
| APEX/risk/activation integration | [Draft PR #3](https://github.com/abutronmall-netizen/abutron-apex/pull/3) | Candidate risk preflight, transactional ON/OFF, CI | No actual broker trade or MT5 order writer |
| Milestone A: first Deriv DEMO 6207 trade | [Tracking issue #4](https://github.com/abutronmall-netizen/abutron-apex/issues/4) | P0 foundation in PR #3 | **BLOCKED: real native writer + receipt + reconciled position** |
| Milestone B: multi-account Deriv and FP Markets | [Tracking issue #5](https://github.com/abutronmall-netizen/abutron-apex/issues/5) | Not operational | **BLOCKED: A, FP broker clock/feed and execution** |
| Milestone C: full operating platform | [Tracking issue #6](https://github.com/abutronmall-netizen/abutron-apex/issues/6) | Not independently verified | **BLOCKED: production service audits, restoration, CRM/billing/Prop Firm/AB Markets** |

The source import checksum is retained in `apex11/SOURCE_IMPORT_AUDIT.json`. Subsequent explicitly reviewed changes use `apex11/SOURCE_PATCH_AUDIT.json`. Do not confuse the repository state with actual running production service state.

### Approved risk policy

- 0.10% risk per trade; 2% total stop-risk cap per account and across each customer's combined Deriv/FP accounts.
- 3% daily equity-loss stop; 20% peak-equity drawdown lockout (persistent manual reset).
- Customer-owned OFF accounts never receive new orders, despite worker restart.
- Unverified positions, prices, stops, entitlements or broker acknowledgements block new entries.
- LIVE trading remains disabled.

### Operational boundary

This GitHub repo does **not** contain the privileged production MT5 writer, CRM DB, payments credentials or running `localhost` services. No GitHub-hosted unit test establishes true broker profit, independent current demo execution or platform recovery certification.

Before production changes: independently inspect source/service ownership, verify encrypted offsite backup and isolated restoration, establish exclusive native writer and rollbacks, then execute genuine first-account **Deriv DEMO 6207** proof only when a fresh qualified signal exists. Do not force a signal or bypass a kill switch for a passing status.
