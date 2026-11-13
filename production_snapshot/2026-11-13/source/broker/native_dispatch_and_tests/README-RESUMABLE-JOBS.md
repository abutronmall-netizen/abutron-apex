# ABUTRON MCP — Recoverable Long Operations
Verified: 2026-11-08 UTC
Implementation: /usr/local/sbin/abutron-mcp-jobctl
Data: /var/lib/abutron-mcp/jobs/<JOB_ID>/{status,output.log}

Purpose: Avoid losing server-side progress when ChatGPT browser response streams
disconnect. The tool runs explicit, non-interactive commands in their own
systemd transient services as unprivileged abutronmcp. No trading order
authority or production deployment permission is granted by this facility.

Usage (invoke through authorized Desktop Commander terminal):
  /usr/local/sbin/abutron-mcp-jobctl start restore-audit-001 -- /usr/bin/python3 /path/to/safe_readonly_check.py
  /usr/local/sbin/abutron-mcp-jobctl status restore-audit-001
  /usr/local/sbin/abutron-mcp-jobctl log restore-audit-001 80
  /usr/local/sbin/abutron-mcp-jobctl list

A JOB_ID is unique and never re-executed. It must start with a lowercase
letter and contain 3-40 lowercase alphanumeric/hyphen characters.
Do not pass passwords, tokens, API keys, or private keys as command arguments.
Inspect the status and output.log before deciding to submit a NEW job ID.

Safety:
  - Root-owned runner, but spawned work always runs as abutronmcp.
  - Runtime 30 minutes, memory 2 GiB, max 64 tasks.
  - NoNewPrivileges; read-only OS; writable job-state directory only.
  - No shell interpretation unless the operator explicitly invokes a shell.
  - Aborted/unknown state must never be marked successful without evidence.
  - This does not repair browser/WebSocket connectivity or automatically
    reconstruct the ChatGPT response.
  - For any trading or deployment change, separately verify approval,
    backups, rollback, account isolation, broker guards, and risk controls.

Verification (2026-11-08):
  reconnect-smoke-20261108 -> SUCCEEDED, EXIT_CODE=0, durable log.
  Duplicate submit -> EXISTING_JOB_NO_REEXECUTION.
  reconnect-fail-20261108 -> FAILED, EXIT_CODE=7, durable log.
  MCP /readyz, /health/control-plane, /health/mcp -> HTTP 200.
  Production tunnel remains unchanged; no live or DEMO orders placed.

Pre-change MCP config backup:
/var/backups/abutron-mcp-resilience-prechange-20261108T145047Z/
Rollback: remove /usr/local/sbin/abutron-mcp-jobctl after confirming no
abutron-mcp-job-*.service remains active; retain job evidence for audit.
