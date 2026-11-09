# ABUTRON portals: production source export (2026-11-09)

This branch captures the current production portal files on the authorized Ubuntu server. It does **not** deploy or activate trading. Files are grouped by their actual source at the time of export.

- `portals/client/active-account-ui/` — current /account/client/ customer UI.
- `portals/client/v7-built-ui/` — compiled V7 client interface.
- `portals/admin/active-crm-ui/` — current /account/admin/ administration UI.
- `portals/admin/v7-built-ui/` — compiled V7 administration interface.
- `portals/apex/active-operator-ui/` — active /apex/ operator interface, static assets, Python API.
- `portals/apex/runtime-modules/` — APEX core top-level runtime Python modules.
- `portals/shared/` — CRM, signup, account entrypoints and V7 backend.
- `databases/` — unencrypted, full-data PostgreSQL SQL dumps and gzip-compressed SQLite snapshots.

The manifest maps each copied file to its original server path and SHA-256. Python caches, environments, platform key files, credential vaults, and external runtime state files are deliberately absent from this source export. All identified portal source files were included. Filesystem references to locally stored credentials remain code references, not credential file contents. The repo is **not** a turnkey one-command deployment; service configuration, OS dependencies, secrets and MT5 terminals are managed separately.

Production files and services were not modified by this export. Never make this repository public while raw database snapshots are present.
