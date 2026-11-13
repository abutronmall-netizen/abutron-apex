#!/usr/bin/python3
"""ABUTRON 6207 V4 read-only production admission audit, NOT a broker supervisor.

No credentials, order permissions, state changes, SQL writes or trading operations.
Never interpret PASS on an individual check as CLAIM/SEND authorization.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sqlite3
import subprocess
import sys
import time

sys.path[:0] = ["/opt/apex-client-portal", "/opt/apex-signup"]
import apex_crm_license_policy as license_policy
import apex_crm_subscriptions as subscriptions
import apex_pricing

CID = "d6fc2524ec373b8d1bc278a8be3ec635"
LOGIN = "32456207"
APEX_DB = "/var/lib/apex-signup/accounts.sqlite3"
WORKER_DIR = Path("/var/lib/private/abutron-client-mt5-" + CID)
SIDECAR_DIR = Path("/var/lib/private/abutron-native-readonly-mt5-6207")
EA = WORKER_DIR / "terminal/MQL5/Experts/ABUTRON/AbutronApexExistingDerivV4_6207.ex5"
APPROVED_SHA256 = "458afad273cb5c2446f52d766d2617cc277bca6b1e990450bb6955c2da64973a"
EXPECTED_RISK = ("0.001", "0.02", "0.03", "0.20")


def safe_file_json(path: Path, *, max_bytes: int = 16384):
    if path.is_symlink():
        raise ValueError("SYMLINK")
    fd = os.open(str(path), os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    try:
        st = os.fstat(fd)
        if st.st_size < 2 or st.st_size > max_bytes or st.st_mode & 0o022:
            raise ValueError("UNSAFE_FILE")
        data = os.read(fd, max_bytes + 1)
        if len(data) != st.st_size:
            raise ValueError("FILE_CHANGED")
        return json.loads(data), st.st_mtime
    finally:
        os.close(fd)


def v7_owner_record():
    # Constant SQL, no caller-controlled query, stdout never includes account PII.
    sql = (
        "SELECT lower(trim(c.email)),a.status,a.bot_tier,a.route_reason "
        "FROM trading_accounts a JOIN customers c ON c.id=a.customer_id "
        "WHERE a.broker_login='32456207' LIMIT 2"
    )
    r = subprocess.run(
        ["runuser", "-u", "postgres", "--", "psql", "-X", "-qAt",
         "-F", "|", "-d", "abutron_v7_release_store", "-c", sql],
        capture_output=True, text=True, timeout=8, check=True,
    )
    rows = [x.split("|", 3) for x in r.stdout.splitlines() if x]
    if len(rows) != 1 or len(rows[0]) != 4:
        raise ValueError("V7_OWNER_RECORD_NOT_UNIQUE")
    return rows[0]


def inspect(now: float | None = None) -> dict:
    now = time.time() if now is None else float(now)
    blocked = []
    checks = {}
    def check(name: str, ok: bool, reason: str):
        checks[name] = bool(ok)
        if not ok:
            blocked.append(reason)

    check("root_readonly_inspector", os.geteuid() == 0, "ROOT_ATTESTOR_REQUIRED")
    owner_email = None
    owner_id = None
    nonce = None
    with sqlite3.connect("file:" + APEX_DB + "?mode=ro", uri=True, timeout=8) as db:
        db.execute("PRAGMA query_only=ON")
        rows = db.execute(
            """SELECT x.id,x.account_id,x.broker,x.environment,x.account_reference,
              x.broker_server,x.status,x.broker_verified_at,x.worker_binding,
              coalesce(t.desired_enabled,0),coalesce(t.effective_enabled,0),
              a.status,a.email
              FROM apex_mt5_connections x JOIN accounts a ON a.id=x.account_id
              LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
              WHERE x.id=? AND x.account_reference=?""", (CID, LOGIN)
        ).fetchall()
        valid = len(rows) == 1
        check("apex_connection_unique", valid, "APEX_6207_OWNER_RECORD_NOT_UNIQUE")
        if valid:
            (cid,owner_id,broker,env,login,server,state,verified,binding,
             desired,effective,client_state,owner_email) = rows[0]
            check("apex_verified_broker_demo",
                  broker == "Deriv" and env == "DEMO" and server == "Deriv-Demo"
                  and state == "CONNECTED" and verified is not None
                  and binding == "abutron-client-mt5-" + CID,
                  "APEX_NATIVE_BROKER_BINDING_NOT_ATTESTED")
            check("apex_customer_approved", client_state == "approved",
                  "APEX_OWNER_NOT_APPROVED")
            check("client_requested_on", desired == 1, "CLIENT_REQUESTED_OFF")
            check("client_effective_on", effective == 1,
                  "CLIENT_EFFECTIVE_EXECUTION_OFF")
            decision = license_policy.connection_decision(db, owner_id, CID)
            check("enterprise_seat_approved",
                  bool(decision and decision.get("license_allows_new_entries") is True
                       and decision.get("license_basis") == "paid"),
                  "APEX_CUSTOMER_LICENSE_OR_SEAT_DENIED")
            subscription = subscriptions.current(db, owner_id)
            entitlement = db.execute(
                "SELECT plan,status,seats,expires_on FROM apex_crm_licenses WHERE account_id=?",
                (owner_id,)
            ).fetchone()
            check("enterprise_subscription_current",
                  bool(subscription and entitlement and entitlement[0] == "Enterprise"
                       and entitlement[1] == "active"
                       and entitlement[2] == apex_pricing.SEATS["Enterprise"]
                       and subscription["plan"] == "Enterprise"
                       and subscription["status"] == "active"
                       and subscription["currency"] == "ZAR"
                       and subscription["billing_interval"] == "monthly"
                       and subscription["amount_minor"] == apex_pricing.PRICES["Enterprise"]
                       and subscription["renewal_on"]
                       and subscription["renewal_on"] >= dt.datetime.now(dt.timezone.utc).date().isoformat()),
                  "APEX_ENTERPRISE_SUBSCRIPTION_NOT_ACTIVE")
            role = db.execute(
                "SELECT role,email_verified_at FROM apex_admin_roles WHERE account_id=?",
                (owner_id,)
            ).fetchone()
            check("apex_owner_mfa",
                  bool(role and role[0] == "SUPERADMIN" and role[1]),
                  "APEX_OWNER_SUPERADMIN_MFA_NOT_PROVEN")
        live = db.execute(
            """SELECT count(*) FROM apex_mt5_connections x
            LEFT JOIN apex_trade_controls t ON x.id=t.connection_id
            WHERE x.environment='LIVE' AND coalesce(t.effective_enabled,0)=1"""
        ).fetchone()[0]
        check("live_orders_disabled", live == 0, "LIVE_EXECUTION_FLAG_PRESENT")

    try:
        v7_email, v7_state, v7_tier, v7_reason = v7_owner_record()
        owner_match = bool(owner_email and hmac.compare_digest(
            owner_email.strip().casefold(), v7_email.strip().casefold()))
        check("same_verified_apex_v7_owner", owner_match,
              "APEX_V7_OWNER_IDENTITY_UNVERIFIED")
        # V7 claim remains deliberately read-only; never promote it.
        check("v7_legacy_claim_readonly",
              v7_state == "PAUSED" and v7_tier == "INELIGIBLE"
              and v7_reason == "verified_existing_owner_deriv_demo_readonly_no_orders",
              "V7_LEGACY_CLAIM_SCOPE_CHANGED")
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError):
        check("same_verified_apex_v7_owner", False,
              "V7_OWNER_ATTESTATION_UNAVAILABLE")

    try:
        worker, modified = safe_file_json(WORKER_DIR / "worker-health.json")
        nonce = worker.get("nonce")
        check("apex_worker_native_identity",
              worker.get("id") == CID and worker.get("broker") == "Deriv"
              and worker.get("mode") == "DEMO"
              and worker.get("server") == "Deriv-Demo"
              and worker.get("status") == "CONNECTED"
              and worker.get("heartbeat_fresh") is True
              and bool(re.fullmatch(r"[a-f0-9]{32}", nonce or ""))
              and -2 <= now-modified <= 20,
              "APEX_6207_WORKER_HEARTBEAT_UNVERIFIED")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        check("apex_worker_native_identity", False,
              "APEX_6207_WORKER_PROOF_UNAVAILABLE")

    try:
        sidecar, modified = safe_file_json(SIDECAR_DIR / "worker-health.json")
        check("read_only_authenticated_deriv_session",
              sidecar.get("broker") == "Deriv"
              and sidecar.get("environment") == "DEMO"
              and sidecar.get("status") == "CONNECTED"
              and sidecar.get("broker_session_identity_verified") is True
              and sidecar.get("execution_authority") is False
              and sidecar.get("orders_submitted") == 0
              and now-float(sidecar.get("broker_checked_utc", 0)) <= 30
              and -2 <= now-modified <= 30,
              "DERIV_6207_INDEPENDENT_SESSION_NOT_VERIFIED")
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        check("read_only_authenticated_deriv_session", False,
              "DERIV_6207_INDEPENDENT_SESSION_UNAVAILABLE")

    try:
        st = EA.lstat()
        if not EA.is_file() or EA.is_symlink() or st.st_size < 20000:
            raise ValueError("INVALID_EX5")
        with EA.open("rb") as f:
            actual_sha = hashlib.file_digest(f, "sha256").hexdigest()
        match = hmac.compare_digest(actual_sha, APPROVED_SHA256)
    except (OSError, ValueError):
        match = False
    check("approved_v4_ex5_installed", match, "APPROVED_V4_EX5_NOT_INSTALLED")
    capability = (WORKER_DIR / "terminal/MQL5/Files" /
                  ("ABUTRON_APEX_NATIVE_V4_CAPABILITY_" + nonce + ".txt")
                  if nonce and re.fullmatch(r"[a-f0-9]{32}", nonce) else None)
    check("native_v4_capability_present",
          bool(capability and capability.is_file() and not capability.is_symlink()
               and -2 <= now-capability.stat().st_mtime <= 12),
          "NATIVE_V4_CHART_CAPABILITY_NOT_ATTESTED")
    # Not enough: capability alone never proves active attached EA, WebRequest,
    # authenticated CLAIM/SEND, kill switch, position risk, or broker reconciliation.
    check("real_v4_supervisor_authorized", False,
          "V4_CRM_MT5_REVISION_FENCED_SUPERVISOR_NOT_CERTIFIED")
    check("cashflow_adjusted_full_portfolio_risk_proven", False,
          "CASHFLOW_ADJUSTED_NATIVE_PORTFOLIO_RISK_NOT_PROVEN")
    check("fresh_apex_m5_signal_broker_verified", False,
          "FRESH_APEX_M5_SIGNAL_NOT_PROVEN")
    return {
        "schema": "abutron.native.v4.6207.readonly.preflight.v1",
        "checked_utc": dt.datetime.fromtimestamp(now, dt.timezone.utc).isoformat(),
        "broker": "Deriv", "account_suffix": "6207", "environment": "DEMO",
        "checks": checks, "blockers": blocked,
        "state": "BLOCKED" if blocked else "INSPECTED_ONLY",
        "order_authorized": False, "orders_submitted": 0,
        "execution_settings_modified": False,
        "source_type": "READ_ONLY_LIVE_HOST_EVIDENCE",
    }


if __name__ == "__main__":
    if os.geteuid() != 0:
        raise SystemExit("ROOT_REQUIRED")
    print(json.dumps(inspect(), sort_keys=True, separators=(",", ":")))
