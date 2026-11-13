# ABUTRON APEX current production source snapshot (13 November 2026)

**Staging branch — not a deployment.** This branch is a temporary private landing area for audited ABUTRON APEX source while creation of the requested *new* GitHub repository is unavailable through the connected GitHub actions.

## Sources

- APEX 1.1 decision engine, contracts and tests
- Customer CRM, admin/client portal, signup, V7 web surfaces
- Deriv and FP Markets MT5 worker, native bridge and MQL5 source
- Order dispatch, broker receipt reconciliation and QA helpers
- Relevant systemd unit definitions and operator scripts

## Provenance

Production host: Ubuntu localhost. Read-only collection performed 2026-11-13 UTC. Files are copied from deployed path locations. A file present on disk does not imply it is the currently running executable or that trading is enabled; inspect systemd and broker receipts separately.

## Hard exclusions

**Never commit** customer database rows, balance/position/order history, passwords, broker tokens, customer PII, TLS/SSH keys, service environment files, private certificates, database dumps, Wine/terminal profiles, logs, proprietary credentials, virtualenvs, compiled Python caches, node_modules or runtime generated evidence. Incomplete/flagged source files remain excluded until manually redacted and reviewed. No prod files or trading settings were changed.

## State warning

The 2026-11-13 service audit showed failed units and the 6207 order dispatcher lacked verified effective CRM ON + broker activation ACK. This source export is **not** evidence of working autonomous execution or restored system health.

## Repository boundary

This is a staging branch of the existing private repository `abutronmall-netizen/abutron-apex`, **not** the separate new repository the owner requested. Transfer this branch's source tree to the dedicated new private repository once repository creation is enabled.
