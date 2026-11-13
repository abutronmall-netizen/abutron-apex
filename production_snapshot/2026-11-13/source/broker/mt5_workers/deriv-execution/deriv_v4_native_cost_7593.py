#!/usr/bin/python3
"""Deriv 7593 DEMO-only broker-native executable cost audit (READ ONLY).

Attests live MQL5 SymbolInfo, current bid/ask and OrderCalcProfit/Margin at the
broker's minimum lot. It never sends an order, issues a CRM ACK or guesses
commission/slippage. Missing/failed source proof keeps the report BLOCKED.
"""
from __future__ import annotations
from datetime import datetime,timezone
import hashlib,json,math,os,re,stat,time
from pathlib import Path

CID="9568525eee306da891258ad98c654919"
ROOT=Path("/var/lib/private/abutron-client-mt5-"+CID)
OUTPUT=Path("/var/lib/abutron-deriv-v4-7593/v4-native-execution-cost-7593.json")
RELEASE=Path("/usr/local/lib/abutron-deriv-v4/7593/AbutronApexExistingDerivV4_7593.ex5")
EXPECTED="ba95b6153cce90833d424cc94c3a776e0788af0bd794816ab20a5443deefa644"
SYMBOLS={"Volatility 10 Index.0","Volatility 25 Index.0",
         "Volatility 50 Index.0","Volatility 75 Index.0",
         "Volatility 100 Index.0"}

def trusted(p,maximum,now,ttl,owner=None):
    if p.is_symlink():raise ValueError("SYMLINK_SOURCE")
    fd=os.open(p,os.O_RDONLY|os.O_NOFOLLOW|os.O_CLOEXEC)
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_nlink!=1 or
            st.st_mode&0o022 or st.st_size<=2 or st.st_size>maximum or
            (owner is not None and st.st_uid!=owner) or
            not -3<=now-st.st_mtime<=ttl):
            raise ValueError("SOURCE_MODE_OR_FRESHNESS_INVALID")
        data=os.read(fd,maximum+1);en=os.fstat(fd)
        if len(data)!=st.st_size or (
            st.st_ino,st.st_size,st.st_mtime_ns,st.st_dev)!=(
            en.st_ino,en.st_size,en.st_mtime_ns,en.st_dev):
            raise ValueError("RACED_NATIVE_SOURCE")
        return data,st
    finally:os.close(fd)

def positive(s,allow_zero=False):
    v=float(s)
    if not math.isfinite(v) or (v<0 if allow_zero else v<=0):
        raise ValueError("NONPOSITIVE_BROKER_NUMBER")
    return v

def inspect(now=None):
    now=time.time() if now is None else now
    hb,hs=trusted(ROOT/"worker-health.json",50000,now,20)
    h=json.loads(hb)
    nonce=h.get("nonce")
    if (h.get("id")!=CID or h.get("broker")!="Deriv" or
        h.get("server")!="Deriv-Demo" or h.get("mode")!="DEMO" or
        h.get("status")!="CONNECTED" or h.get("heartbeat_fresh") is not True or
        not isinstance(nonce,str) or not re.fullmatch(r"[0-9a-f]{32}",nonce)):
        raise ValueError("BROKER_WORKER_NOT_ATTESTED")
    rel,_=trusted(RELEASE,250000,now,365*86400,0)
    if hashlib.sha256(rel).hexdigest()!=EXPECTED:
        raise ValueError("PINNED_RELEASE_HASH_INVALID")
    loaded=ROOT/"terminal/MQL5/Experts/ABUTRON/AbutronApexExistingDerivV4_7593.ex5"
    binary,_=trusted(loaded,250000,now,365*86400)
    if hashlib.sha256(binary).hexdigest()!=EXPECTED:
        raise ValueError("CURRENT_NATIVE_EA_NOT_PINNED")
    evidence=ROOT/"terminal/MQL5/Files/ABUTRON"/("v4-native-costs-"+nonce+".txt")
    raw,st=trusted(evidence,14000,now,22)
    lines=raw.decode("utf-8-sig").splitlines()
    if (len(lines)!=18 or
        lines[:6]!=["ABUTRON_V4_NATIVE_EXECUTION_COSTS_V1",nonce,
                    "6357593","Deriv-Demo","DEMO","USD"] or
        lines[10]!="5" or
        lines[11]!="COMMISSION_AND_REALIZED_SLIPPAGE_NOT_CERTIFIED" or
        lines[17]!="END\t5"):
        raise ValueError("NATIVE_COST_PROTOCOL_INVALID")
    stamp=int(lines[6])
    if not -3<=now-stamp<=22:
        raise ValueError("NATIVE_COST_BROKER_CLOCK_UNVERIFIED")
    equity=positive(lines[7]);balance=positive(lines[8],allow_zero=True)
    free_margin=positive(lines[9],allow_zero=True)
    observed={}
    for line in lines[12:17]:
        a=line.split("\t")
        if len(a)!=22 or a[0]!="S" or a[1] not in SYMBOLS or a[1] in observed:
            raise ValueError("NATIVE_COST_SYMBOL_OR_FIELDS_INVALID")
        symbol=a[1]
        bid,ask=(positive(x) for x in a[2:4])
        tick_age_ms=int(a[4])
        minlots,lotstep,maxlots,ticksize,point,contract,vprofit,vloss=(
            positive(x,allow_zero=(i>=6)) for i,x in enumerate(a[5:13]))
        buy_tick_loss,sell_tick_loss,buy_spread,sell_spread=map(float,a[13:17])
        buy_margin,sell_margin=map(float,a[17:19])
        stops,freeze=(int(x) for x in a[19:21])
        probe_ticks=int(a[21])
        if (not 0<bid<=ask or ask-bid>ask*.1 or
            not -3000<=tick_age_ms<=90000 or
            minlots>maxlots or lotstep>maxlots or point>ticksize*1000 or
            stops<0 or freeze<0 or probe_ticks not in (1,10,100,1000,10000,100000,1000000,10000000,100000000) or
            not all(math.isfinite(x) and x<=0 for x in
                    (buy_tick_loss,sell_tick_loss,buy_spread,sell_spread)) or
            not all(math.isfinite(x) and x>=0 for x in (buy_margin,sell_margin)) or
            buy_tick_loss==0 or sell_tick_loss==0):
            raise ValueError("NONEXECUTABLE_BROKER_COST_PROOF")
        observed[symbol]={
            "bid":bid,"ask":ask,"tick_age_ms":tick_age_ms,
            "min_lots":minlots,"volume_step":lotstep,"max_lots":maxlots,
            "tick_size":ticksize,"point":point,"contract_size":contract,
            "broker_tick_value_profit":vprofit,"broker_tick_value_loss":vloss,
            "buy_probe_native_ordercalcprofit_usd":buy_tick_loss,
            "pnl_probe_displacement_ticks":probe_ticks,
            "normalized_buy_usd_loss_per_tick_from_broker_probe":-buy_tick_loss/probe_ticks,
            "sell_probe_native_ordercalcprofit_usd":sell_tick_loss,
            "normalized_sell_usd_loss_per_tick_from_broker_probe":-sell_tick_loss/probe_ticks,
            "buy_cross_spread_native_ordercalcprofit_usd":buy_spread,
            "sell_cross_spread_native_ordercalcprofit_usd":sell_spread,
            "buy_minlot_native_ordercalcmargin_usd":buy_margin,
            "sell_minlot_native_ordercalcmargin_usd":sell_margin,
            "stops_level_points":stops,"freeze_level_points":freeze,
            "spread_in_price_units":ask-bid}
    if set(observed)!=SYMBOLS:
        raise ValueError("NOT_ALL_FIVE_BROKER_INSTRUMENTS_VERIFIED")
    return {
        "schema":"abutron.deriv7593.native_ordercalcprofit_costs.readonly.v1",
        "checked_utc":datetime.fromtimestamp(now,timezone.utc).isoformat(),
        "state":"VERIFIED_NATIVE_SPREAD_AND_PROFIT_CALC_NO_ORDER_AUTHORITY",
        "environment":"DEMO","account_suffix":"7593","worker_nonce":nonce,
        "broker_source_sha256":hashlib.sha256(raw).hexdigest(),
        "native_ea_sha256":EXPECTED,"native_sample_utc":stamp,
        "account_equity_usd":equity,"account_balance_usd":balance,
        "account_free_margin_usd":free_margin,
        "instruments":observed,
        "native_bid_ask_and_ordercalcprofit_verified":True,
        "native_minlot_ordercalcmargin_verified":True,
        "historical_commission_certified":False,
        "realized_slippage_certified":False,
        "full_execution_costs_certified":False,
        "native_ordercheck_for_exact_proposal_certified":False,
        "customer_wide_risk_certified":False,
        "crm_broker_ack_certified":False,
        "live_authorized":False,"order_submission_attempted":False}

def main():
    if os.geteuid()!=0 or OUTPUT.parent.is_symlink() or (
        OUTPUT.parent.stat().st_uid!=0 or OUTPUT.parent.stat().st_mode&0o077):
        raise SystemExit("ROOT_TRUSTED_EVIDENCE_DIR_REQUIRED")
    now=time.time()
    try:doc=inspect(now)
    except Exception as exc:
        doc={"schema":"abutron.deriv7593.native_ordercalcprofit_costs.readonly.v1",
             "checked_utc":datetime.fromtimestamp(now,timezone.utc).isoformat(),
             "state":"BLOCKED_UNVERIFIED_BROKER_NATIVE_COSTS",
             "reason":type(exc).__name__+":"+str(exc)[:120],
             "environment":"DEMO","account_suffix":"7593",
             "native_bid_ask_and_ordercalcprofit_verified":False,
             "full_execution_costs_certified":False,
             "customer_wide_risk_certified":False,
             "crm_broker_ack_certified":False,
             "order_submission_attempted":False}
    temp=OUTPUT.parent/(".v4-native-cost-evidence-"+str(os.getpid())+".tmp")
    fd=os.open(temp,os.O_WRONLY|os.O_EXCL|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"w") as out:
            json.dump(doc,out,sort_keys=True,separators=(",",":"),allow_nan=False)
            out.write("\n");out.flush();os.fsync(out.fileno())
        os.replace(temp,OUTPUT)
    finally:temp.unlink(missing_ok=True)
    print(json.dumps({"state":doc["state"],
                      "instrument_count":len(doc.get("instruments",{})),
                      "order_submission_attempted":False,
                      "reason":doc.get("reason")},sort_keys=True))

if __name__=="__main__":main()
