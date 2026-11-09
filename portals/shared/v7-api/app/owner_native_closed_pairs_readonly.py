"""Deterministic, fail-closed reconciliation of broker-native MT5 deal events.
No database writes, no trading API, no account management, no secrets.
"""
from collections import defaultdict
from datetime import datetime,timezone
from decimal import Decimal,InvalidOperation
from pathlib import Path

class ReconcileRejected(ValueError):pass

def ensure(cond,reason):
    if not cond:raise ReconcileRejected(reason)

def cash(value):
    try:r=Decimal(value)
    except (ValueError,TypeError,InvalidOperation):raise ReconcileRejected("INVALID_MONEY")
    ensure(r.is_finite() and abs(r)<Decimal("1000000000"),"UNTRUSTED_MONEY")
    return r

def reconcile(source:dict)->dict:
    ensure(source.get("schema")=="ABUTRON_V7_NATIVE_ACCOUNT_SNAPSHOT_V1"
      and source.get("account_login")=="32456207" and source.get("server")=="Deriv-Demo"
      and source.get("currency")=="USD" and source.get("mode")=="DEMO"
      and source.get("trade_execution_authorized") is False
      and source.get("broker_trade_reconciliation_certified") is False
      and source.get("history_is_bounded_not_lifetime") is True,
      "SOURCE_NOT_APPROVED")
    ensure(source.get("open_position_count")==0 and source.get("pending_order_count")==0,
      "ACTIVE_POSITIONS_OR_ORDERS_NOT_COVERED")
    es=source.get("history_deals")
    ensure(type(es)==list and 0<len(es)<=2000
      and len(es)==source.get("history_deal_count"),"HISTORY_INCOMPLETE")
    begin=source["history_from_unix"];end=source["history_to_unix"]
    ensure(type(begin)==int and type(end)==int and 0<begin<end<=source["captured_unix"],
           "INVALID_HISTORY_WINDOW")
    ids=set();groups=defaultdict(list);adjustments=[]
    for e in es:
        ticket=e["ticket"];ensure(ticket.isdigit() and ticket not in ids,"DUPLICATE_DEAL_TICKET")
        ids.add(ticket)
        ensure(begin<=e["time_unix"]<=end,"EVENT_OUTSIDE_WINDOW")
        ensure(e["order_id"].isdigit() and e["position_id"].isdigit(),"INVALID_ORDER_OR_POSITION_ID")
        if e["deal_type"] in (0,1):
            ensure(e["deal_entry"] in (0,1),"UNSUPPORTED_REVERSAL_OR_PARTIAL")
            ensure(e["position_id"]!="0" and e["symbol"] and cash(e["volume"])>0
                and cash(e["price"])>0,"INVALID_TRADING_DEAL")
            groups[e["position_id"]].append(e)
        elif e["deal_type"]==2 and e["position_id"]=="0":
            adjustments.append(e)
        else:raise ReconcileRejected("OTHER_BROKER_FEES_OR_ADJUSTMENTS_NOT_RECONCILED")
    ensure(groups and len(adjustments)==1,"UNEXPECTED_NATIVE_LIFECYCLE_SHAPE")
    out=[]
    for position,items in groups.items():
        inbound=[e for e in items if e["deal_entry"]==0]
        outbound=[e for e in items if e["deal_entry"]==1]
        ensure(len(items)==2 and len(inbound)==1 and len(outbound)==1,
               "PARTIAL_OR_MULTIPLE_FILL_UNSUPPORTED")
        a=inbound[0];b=outbound[0]
        ensure(a["deal_type"] in (0,1) and b["deal_type"]==1-a["deal_type"],
               "INVALID_CLOSING_SIDE")
        ensure(a["symbol"]==b["symbol"] and cash(a["volume"])==cash(b["volume"])
            and a["time_unix"]<=b["time_unix"],"UNBALANCED_OR_UNORDERED_POSITION")
        net=sum((cash(e[k]) for e in items
                 for k in ("gross_profit","commission","fee","swap")),Decimal(0))
        comm=sum((cash(e[k]) for e in items for k in ("commission","fee")),Decimal(0))
        sw=sum((cash(e["swap"]) for e in items),Decimal(0))
        out.append({
          "broker_ticket":position,
          "broker_order_id":b["order_id"],
          "symbol":a["symbol"],
          "direction":"BUY" if a["deal_type"]==0 else "SELL",
          "volume":str(cash(a["volume"])),"lifecycle":"CLOSED",
          "open_price":str(cash(a["price"])),"close_price":str(cash(b["price"])),
          "net_pnl":str(net),"commission":str(comm),"swap":str(sw),
          "pnl_currency":"USD",
          "opened_at":datetime.fromtimestamp(a["time_unix"],timezone.utc).isoformat(),
          "closed_at":datetime.fromtimestamp(b["time_unix"],timezone.utc).isoformat(),
          "entry_deal":a["ticket"],"exit_deal":b["ticket"]})
    out.sort(key=lambda x:(x["opened_at"],x["broker_ticket"]))
    deposit=sum((sum((cash(x[k]) for k in ("gross_profit","commission","fee","swap")),Decimal(0)) for x in adjustments),Decimal(0))
    pnl=sum((cash(x["net_pnl"]) for x in out),Decimal(0))
    ensure(deposit+pnl==cash(source["balance"]),"BROKER_BALANCE_NOT_RECONCILED")
    return {"schema":"ABUTRON_V7_NATIVE_CLOSED_TRADES_RECONCILED_V1",
      "account_login":"32456207","server":"Deriv-Demo",
      "capture_unix":source["captured_unix"],
      "source_deal_events":len(es),
      "position_pairs":len(out),"nontrade_balance_events":len(adjustments),
      "funding_usd":str(deposit),"trading_net_usd":str(pnl),
      "account_balance_usd":str(cash(source["balance"])),
      "complete_position_pairs":out,
      "execution_authorized":False,
      "history_is_bounded_not_lifetime":True}
