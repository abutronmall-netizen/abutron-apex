#!/usr/bin/python3
"""Read-only Deriv DEMO 6207 MT5 WebRequest full-profile rebuild attestation.

An EA-generated capability is only emitted after a genuine native MT5 WebRequest
HTTP 200 and parseable server revision. The check never authorizes trading.
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
import time
from pathlib import Path

CID = "d6fc2524ec373b8d1bc278a8be3ec635"
STATE = Path("/var/lib/abutron-client-mt5-" + CID)
OUTPUT = Path("/var/lib/abutron-v4-broker-crm-supervisor-6207/mt5-webrequest-rebuild-attestation.json")
RELEASE_HASH = "0581985fdd90b14349468889880cd3b7b4cba83405be8fc874dc6947e37162fe"
EA_REL = "MQL5/Experts/ABUTRON/AbutronApexExistingDerivV4_6207.ex5"
CAP_PREFIX = "ABUTRON_APEX_NATIVE_V4_CAPABILITY_"
EXPECTED_PREFIX = ["APEX_NATIVE_REVISION_FENCED_CAPABILITY_V4", None, "32456207", "Deriv-Demo", "DEMO"]
NOW = time.time()

def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def verify_profile(path: Path, current: bool) -> tuple[dict, str]:
    if path.is_symlink() or not path.is_dir():
        raise ValueError("PROFILE_NOT_REAL_DIRECTORY")
    ea = path / EA_REL
    if ea.is_symlink() or not ea.is_file() or digest(ea) != RELEASE_HASH:
        raise ValueError("V4_BINARY_INTEGRITY_INVALID")
    folder = path / "MQL5/Files"
    caps = list(folder.glob(CAP_PREFIX + "*.txt"))
    if len(caps) != 1:
        raise ValueError("CAPABILITY_FILE_COUNT_NOT_ONE")
    cap = caps[0]
    if cap.is_symlink() or not cap.is_file():
        raise ValueError("CAPABILITY_NOT_REGULAR_FILE")
    lines = cap.read_text(encoding="utf-8-sig").splitlines()
    if (len(lines) != 10 or lines[0] != EXPECTED_PREFIX[0]
        or lines[2:5] != EXPECTED_PREFIX[2:5]
        or not len(lines[1]) == 32
        or any(ch not in "0123456789abcdef" for ch in lines[1])
        or cap.stem != CAP_PREFIX + lines[1]
        or not lines[5].isdigit() or int(lines[5]) < 1
        or not lines[6].isdigit()
        or abs(int(lines[6]) - cap.stat().st_mtime) > 70
        or lines[7:] != ["0.10", "OFF_REVISION_CHECK_AT_CONSUME", "LIVE_FORBIDDEN"]):
        raise ValueError("NATIVE_WEBREQUEST_CAPABILITY_INVALID")
    age = NOW - cap.stat().st_mtime
    if age < -5 or (current and age > 35):
        raise ValueError("CURRENT_NATIVE_CAPABILITY_STALE_OR_FUTURE")
    item = {
        "profile": path.name, "native_webrequest_http200": True,
        "native_revision": int(lines[5]),
        "ea_release_hash_matched": True,
        "nonce_sha256_prefix": hashlib.sha256(lines[1].encode("ascii")).hexdigest()[:16],
        "capability_timestamp_utc": int(cap.stat().st_mtime),
    }
    return item, lines[1]

def evaluate() -> dict:
    checks = []
    issues = []
    current = STATE / "terminal"
    retired = sorted(STATE.glob("terminal-retired-*"), key=lambda p: p.name)
    # Only the immediately previous complete profile proves this SAME EA build
    # survived a full worker-profile rebuild; older QA builds are not equivalent.
    selected = retired[-1:]
    if len(selected) < 1:
        issues.append("NO_PRIOR_PROFILE_FOR_SAME_RELEASE_REBUILD")
    nonces = set()
    items = []
    for path in selected + [current]:
        try:
            record, nonce = verify_profile(path, path == current)
            if nonce in nonces:
                raise ValueError("NONCE_REUSED_ACROSS_PROFILES")
            nonces.add(nonce)
            items.append(record)
            checks.append(path.name + ":PASS")
        except Exception as exc:
            issues.append(path.name + ":" + str(exc))
    try:
        hpath = STATE / "worker-health.json"
        if hpath.is_symlink():
            raise ValueError("WORKER_HEALTH_SYMLINK")
        health = json.loads(hpath.read_text())
        live_caps = list((current / "MQL5/Files").glob(CAP_PREFIX + "*.txt"))
        valid = (health.get("id") == CID
                 and health.get("broker") == "Deriv"
                 and health.get("server") == "Deriv-Demo"
                 and health.get("mode") == "DEMO"
                 and health.get("status") == "CONNECTED"
                 and health.get("heartbeat_fresh") is True
                 and isinstance(health.get("verified_at"), int)
                 and -5 <= NOW - health["verified_at"] <= 35
                 and len(live_caps) == 1
                 and live_caps[0].stem == CAP_PREFIX + health.get("nonce", ""))
        if not valid:
            raise ValueError("LIVE_WORKER_HEALTH_OR_NONCE_MISMATCH")
        checks.append("CURRENT_WORKER_BROKER_BOUND:PASS")
    except Exception as exc:
        issues.append("LIVE_WORKER:" + str(exc))
    certified = not issues and len(items) == 2
    return {
        "schema": "abutron.mt5.deriv6207.webrequest.rebuild-attestation.v1",
        "checked_utc_epoch": int(NOW), "environment": "DEMO",
        "account_suffix": "6207",
        "webrequest_rebuild_survivability_verified": certified,
        "native_http_status_proof_verified": certified,
        "distinct_complete_profiles_checked": len(items),
        "profile_evidence": items, "checks": checks, "blockers": issues,
        "state": ("PASS_REBUILT_PROFILE_NATIVE_HTTP200"
                  if certified else "BLOCKED_FAIL_CLOSED"),
        "crm_ack_certified_by_this_check": False,
        "customer_wide_risk_certified_by_this_check": False,
        "broker_order_ack_certified_by_this_check": False,
        "full_execution_costs_certified_by_this_check": False,
        "trading_authorized_by_this_check": False
    }

def main() -> int:
    result = evaluate()
    if OUTPUT.parent.is_symlink() or not OUTPUT.parent.is_dir():
        raise RuntimeError("REPORT_DIRECTORY_UNSAFE")
    temp = OUTPUT.parent / (".mt5-rebuild-attestation-" + str(os.getpid()) + ".tmp")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(result, f, indent=2, sort_keys=True)
            f.write("\n")
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp, OUTPUT)
    finally:
        temp.unlink(missing_ok=True)
    print(json.dumps({
        "status": result["state"],
        "complete_profiles": result["distinct_complete_profiles_checked"],
        "checks": result["checks"], "blockers": result["blockers"]
    }, sort_keys=True))
    return 0 if result["webrequest_rebuild_survivability_verified"] else 2

if __name__ == "__main__":
    sys.exit(main())
