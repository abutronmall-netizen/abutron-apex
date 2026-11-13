"""Root-owned minimal APEX DEMO telemetry snapshots for isolated Wine Python.
No secrets, account IDs, passwords, keys or trading actions are copied.
"""
from pathlib import Path
import json, os, tempfile

ROOT=Path("/opt/apex/runtime/demo-feed")
FILES={
 "policy":"/etc/apex/trading-policy.json",
 "account":"/var/lib/apex/mt5-market/deriv_demo_account.json",
 "scanner":"/var/lib/apex/scanner/latest.json",
 "market":"/var/lib/apex/mt5-market/deriv_demo_bars.json",
}

def atomic(name,obj):
    fd,tmp=tempfile.mkstemp(prefix=".feed-",dir=str(ROOT))
    try:
        with os.fdopen(fd,"w") as stream:
            json.dump(obj,stream,separators=(",",":"),allow_nan=False)
            stream.flush();os.fsync(stream.fileno())
        os.chmod(tmp,0o644)
        os.replace(tmp,ROOT/(name+".json"))
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    os.chmod(ROOT,0o755)
    if ROOT.stat().st_uid != 0:raise RuntimeError("FEED_DIRECTORY_NOT_ROOT_OWNED")
    docs={key:json.loads(Path(path).read_text()) for key,path in FILES.items()}
    p=docs["policy"];a=docs["account"];s=docs["scanner"];m=docs["market"]
    if p.get("schema")!="apex.trading.policy.v1" or p.get("environment")!="DERIV_DEMO":
        raise RuntimeError("POLICY_SOURCE_INVALID")
    if a.get("source")!="Deriv DEMO MT5" or m.get("source")!="Deriv DEMO MT5" or s.get("source")!="Deriv DEMO MT5":
        raise RuntimeError("BROKER_SOURCE_MISMATCH")
    policy={k:p.get(k) for k in ("schema","environment","live_trading","automated_demo_execution","max_demo_loss_usd","max_concurrent_positions","max_positions_per_symbol")}
    account={k:a.get(k) for k in ("schema","source","generated_at_utc","execution_enabled","live_enabled","history_complete")}
    account["account"]={k:a.get("account",{}).get(k) for k in
        ("mode","broker","currency","equity_usd","balance_usd","gross_negative_deal_cashflows_today_usd",
         "floating_profit_usd","open_positions","allow_trading_account","allow_trading_terminal")}
    account["positions"]=[{k:x.get(k) for k in ("ticket","symbol","sl","tp")} for x in a.get("positions",[])]
    scanner={k:s.get(k) for k in ("schema","source","generated_at_utc","orders_enabled","symbol_count")}
    scanner["instruments"]=[{k:x.get(k) for k in ("symbol","proposal","m5_signal","last_closed_m5")}
                             for x in s.get("instruments",[])]
    market={k:m.get(k) for k in ("schema","source","generated_at_utc","execution_enabled","data")}
    # Root owns the source of USD lot/SL/TP configuration and Wine sees a
    # least-privilege copy. No broker IDs or secrets are embedded.
    profile_path=Path("/opt/apex/runtime/APEX_DERIV_USD_PROFILE_ACTIVE_v1.json")
    if profile_path.stat().st_uid!=0 or profile_path.stat().st_mode&0o022:
        raise RuntimeError("USD_PROFILE_PERMISSIONS_NOT_TRUSTED")
    usd_profile=json.loads(profile_path.read_text(encoding="utf-8"))
    # Pure Linux-side validator: no Windows-only MetaTrader5 import here.
    from apex_fast_scanner import EXPECTED
    if (usd_profile.get("schema")!="apex.deriv.user_profile.review.v1" or
        usd_profile.get("status")!="ACTIVE_DERIV_DEMO_USD_GROSS" or
        usd_profile.get("source_sha256")!="f965a4f6cf9380a3c48401480d49b2af2b235243f82890f8fc14d01073ad1d1d" or
        usd_profile.get("lot_unit")!="lots" or
        usd_profile.get("stop_loss_unit")!="USD_GROSS_BROKER_PNL" or
        usd_profile.get("take_profit_unit")!="USD_GROSS_BROKER_PNL" or
        usd_profile.get("live_trading_allowed") is not False):
        raise RuntimeError("USD_PROFILE_SOURCE_OR_UNIT_UNVERIFIED")
    rows=usd_profile.get("rows")
    if not isinstance(rows,list) or len(rows)!=13 or set(r[0] for r in rows)!=set(EXPECTED):
        raise RuntimeError("USD_PROFILE_SYMBOL_COVERAGE_INCOMPLETE")
    import math
    if any(not isinstance(r,list) or len(r)!=4 or any(
        type(x) not in (int,float) or not math.isfinite(x) or x<=0
        for x in r[1:]) for r in rows):
        raise RuntimeError("USD_PROFILE_BAD_VALUES")
    for name,obj in (("policy",policy),("account",account),("scanner",scanner),
                     ("market",market),("usd_profile",usd_profile)):
        atomic(name,obj)
    print(json.dumps({"status":"STAGED_READ_ONLY","policy_demo":policy["automated_demo_execution"],
                      "cap_usd":policy["max_demo_loss_usd"],"scanner_instruments":len(scanner["instruments"]),
                      "broker_symbols":len(market.get("data",{}))}),flush=True)

if __name__=="__main__":main()
