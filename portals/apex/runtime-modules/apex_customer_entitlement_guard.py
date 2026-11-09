"""APEX customer MT5 entry authorization sidecar.

Not the owner Deriv DEMO controller. No new orders are submitted by this
module unless called by a separate authenticated customer MT5 worker.
For every NEW entry, fail closed on identity, CRM licensing, server or token.
Never call this guard to close/reduce/protect existing positions.
"""
from __future__ import annotations
import base64,json,re,secrets,time,urllib.request,urllib.error
from pathlib import Path
from cryptography.hazmat.primitives import serialization

PRIVATE=Path("/etc/apex/customer-entitlement/worker.pem")
URL="https://abutronfx.online/account/api/client/worker/entry-check"
class CustomerEntryDenied(RuntimeError):pass
def canonical(payload):
    return json.dumps(payload,sort_keys=True,separators=(",",":"),allow_nan=False).encode()
def verified_identity(context,account,terminal):
    """Live broker MT5 account_info() and terminal_info() required, not CRM claims."""
    for field in ("account_id","connection_id","broker","environment","platform",
                  "account_reference","broker_server","worker_binding"):
        if not isinstance(context.get(field),str) or not context[field]:
            raise CustomerEntryDenied("CUSTOMER_BINDING_MISSING")
    if context["platform"]!="MT5" or context["environment"]!="DEMO":
        raise CustomerEntryDenied("CUSTOMER_LIVE_EXECUTION_NOT_ENABLED")
    if context["broker"] not in ("Deriv","IC Markets","FP Markets"):
        raise CustomerEntryDenied("BROKER_NOT_APPROVED")
    if account is None or terminal is None or not bool(getattr(terminal,"connected",False)):
        raise CustomerEntryDenied("BROKER_SESSION_UNAVAILABLE")
    if str(getattr(account,"login",""))!=context["account_reference"]:
        raise CustomerEntryDenied("MT5_ACCOUNT_NUMBER_MISMATCH")
    if str(getattr(account,"server",""))!=context["broker_server"]:
        raise CustomerEntryDenied("MT5_BROKER_SERVER_MISMATCH")
    company=str(getattr(account,"company","")).lower()
    brand={"Deriv":"deriv","IC Markets":"ic markets","FP Markets":"fp markets"}[context["broker"]]
    if brand not in company:
        raise CustomerEntryDenied("MT5_BROKER_COMPANY_MISMATCH")
    # MT5 ACCOUNT_TRADE_MODE_DEMO=0; intentionally reject REAL and CONTEST.
    if getattr(account,"trade_mode",None)!=0:
        raise CustomerEntryDenied("NOT_MT5_DEMO_ACCOUNT")
    if not (bool(getattr(account,"trade_allowed",False)) and
            bool(getattr(terminal,"trade_allowed",False)) and
            not bool(getattr(terminal,"tradeapi_disabled",True))):
        raise CustomerEntryDenied("BROKER_TRADING_PERMISSION_OFF")
def check_new_entry(context,account,terminal,opener=None,now=None):
    verified_identity(context,account,terminal)
    if not PRIVATE.is_file():raise CustomerEntryDenied("WORKER_SIGNING_KEY_MISSING")
    now=int(time.time() if now is None else now)
    payload={**{key:context[key] for key in ("account_id","connection_id","broker","platform",
       "environment","account_reference","broker_server","worker_binding")},
       "timestamp":now,"nonce":secrets.token_hex(16)}
    try:
        key=serialization.load_pem_private_key(PRIVATE.read_bytes(),password=None)
        signature=base64.b64encode(key.sign(canonical(payload))).decode()
        req=urllib.request.Request(URL,method="POST",data=canonical(payload),
            headers={"Content-Type":"application/json","X-APEX-Worker-Signature":signature})
        response=opener or urllib.request.urlopen
        with response(req,timeout=6) as r:
            if r.status!=200:raise CustomerEntryDenied("CRM_SERVICE_HTTP_ERROR")
            body=json.loads(r.read(4096).decode())
        if (body.get("schema")!="apex.customer.entry.v1" or
            body.get("nonce")!=payload["nonce"] or
            body.get("connection_id")!=payload["connection_id"] or
            body.get("live_trading_enabled") is not False or
            body.get("allowed") is not True or
            body.get("reason_codes")!=[] or
            type(body.get("max_age_seconds")) is not int or not 1<=body["max_age_seconds"]<=10):
            raise CustomerEntryDenied("CRM_CUSTOMER_ENTITLEMENT_DENIED")
        if abs(time.time()-now)>body["max_age_seconds"]:
            raise CustomerEntryDenied("CRM_ENTITLEMENT_STALE")
        return {"allowed":True,"connection_id":context["connection_id"],
                "nonce":payload["nonce"],"protective_exits_preserved":True}
    except CustomerEntryDenied:raise
    except (OSError,ValueError,TypeError,KeyError,urllib.error.URLError) as e:
        raise CustomerEntryDenied("CRM_ENTITLEMENT_UNAVAILABLE") from e
def guarded_new_customer_order(mt5,context,request):
    """Only sanctioned customer submission entrypoint; no bypass on bad response."""
    if request.get("action")!=mt5.TRADE_ACTION_DEAL:
        raise CustomerEntryDenied("NOT_A_NEW_ENTRY_DEAL")
    verified=check_new_entry(context,mt5.account_info(),mt5.terminal_info())
    if not verified["allowed"]:raise CustomerEntryDenied("CRM_DENIED")
    # The account identity can change between the authorization and the send.
    verified_identity(context,mt5.account_info(),mt5.terminal_info())
    return mt5.order_send(request)
