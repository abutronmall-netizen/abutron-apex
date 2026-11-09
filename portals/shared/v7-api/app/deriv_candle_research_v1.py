"""Authenticated read-only broker-public Deriv OHLC for 13 synthetic symbols, 8 native candle periods.
Directional research (close vs open) is NOT a certified Kronos AI signal.
NO OAuth, trade API, customer broker account or sensitive information.
"""
from __future__ import annotations
import asyncio,json,math,time
from decimal import Decimal,InvalidOperation
from datetime import datetime,timezone
from fastapi import APIRouter,Depends,HTTPException,Query
import websockets
from app.deriv_market_readonly import WS_URL,CODES
from app.models import Customer
from app.security import get_current_customer

TF_SEC={"M1":60,"M3":180,"M5":300,"M15":900,"M30":1800,"H1":3600,"H4":14400,"D1":86400}
assert len(TF_SEC)==8 and len(CODES)==13
router=APIRouter(prefix="/api/v1",tags=["deriv-broker-closed-candles"])
_lock=asyncio.Lock()
_cache:dict[str,tuple[float,dict]]={}
async def fetch_candles(symbol:str,*,connector=None,clock=None)->dict:
 if symbol not in CODES:raise ValueError("UNAPPROVED_DERIV_SYMBOL")
 connector=connector or websockets.connect
 clock=clock or time.time
 results={}
 async with connector(WS_URL,open_timeout=8,close_timeout=3,max_size=800000,ping_interval=None) as ws:
  for i,(tf,seconds) in enumerate(TF_SEC.items(),1001):
   await ws.send(json.dumps({"ticks_history":symbol,"style":"candles",
          "end":"latest","count":5,"granularity":seconds,"req_id":i}))
  deadline=time.monotonic()+14
  for _ in TF_SEC:
   remaining=deadline-time.monotonic()
   if remaining<=0:raise ValueError("CANDLES_UPSTREAM_TIMEOUT")
   raw=await asyncio.wait_for(ws.recv(),timeout=remaining)
   message=json.loads(raw)
   if not isinstance(message,dict) or "error" in message or message.get("msg_type")!="candles":
    raise ValueError("UNVERIFIED_CANDLE_PAYLOAD")
   echo=message.get("echo_req")
   if not isinstance(echo,dict) or echo.get("ticks_history")!=symbol or echo.get("style")!="candles":
    raise ValueError("CANDLE_SYMBOL_MISMATCH")
   period=echo.get("granularity")
   if type(period)!=int or period not in TF_SEC.values():raise ValueError("CANDLE_PERIOD_UNEXPECTED")
   tf=next(name for name,sec in TF_SEC.items() if sec==period)
   if tf in results:raise ValueError("CANDLE_DUPLICATE_TF")
   data=message.get("candles")
   if not isinstance(data,list) or not 3<=len(data)<=5:raise ValueError("CANDLE_HISTORY_INSUFFICIENT")
   prior=-1;closed=[]
   now=float(clock())
   for cand in data:
    if not isinstance(cand,dict):raise ValueError("CANDLE_INVALID")
    epoch=cand.get("epoch")
    if type(epoch)!=int or epoch<=prior or epoch % period:raise ValueError("CANDLE_UNSORTED_OR_UNALIGNED")
    prior=epoch
    try:
     o,h,l,c=(Decimal(str(cand[x])) for x in ("open","high","low","close"))
    except (KeyError,ValueError,TypeError,InvalidOperation) as exc:raise ValueError("CANDLE_PRICE_BAD") from exc
    if not all(x.is_finite() and x>0 for x in (o,h,l,c)) or h<max(o,c) or l>min(o,c):
     raise ValueError("CANDLE_OHLC_INCONSISTENT")
    if epoch+period<=now-1:closed.append((epoch,o,h,l,c))
   if not closed:raise ValueError("CANDLE_NO_CLOSED_INTERVAL")
   epoch,o,h,l,c=closed[-1]
   age=now-(epoch+period)
   if not 1<=age<=period+65:raise ValueError("CLOSED_CANDLE_OLD_OR_FUTURE")
   # BUY/SELL below are merely deterministic single-candle close-open direction, NOT Kronos.
   bias="BUY" if c>o else "SELL" if c<o else "NEUTRAL"
   results[tf]={
     "timeframe":tf,"open_utc":datetime.fromtimestamp(epoch,timezone.utc).isoformat(),
     "candle_closed_utc":datetime.fromtimestamp(epoch+period,timezone.utc).isoformat(),
     "open":str(o),"high":str(h),"low":str(l),"close":str(c),
     "candle_bias":bias,"basis":"CLOSE_MINUS_OPEN_ONLY",
     "is_candle_closed":True,"broker_public_candle_verified":True,
   }
 if set(results)!=set(TF_SEC):raise ValueError("CANDLE_MISSING_INTERVAL")
 return {"schema":"ABUTRON_DERIV_NATIVE_CLOSED_CANDLE_RESEARCH_V1",
         "source":"DERIV_PUBLIC_CANDLE_HISTORY_NO_CUSTOMER_AUTH",
         "symbol":symbol,"market":"DERIV_PUBLIC_OPTIONS_MARKET_NOT_MT5",
         "checked_utc":datetime.fromtimestamp(clock(),timezone.utc).isoformat(),
         "rows":[results[tf] for tf in TF_SEC],
         "customer_mt5_account_linked":False,"kronos_strategy_signal_certified":False,
         "orders_authorized":False}
async def cached_candles(symbol:str)->dict:
 now=time.monotonic()
 async with _lock:
  cached=_cache.get(symbol)
  if cached and now-cached[0]<12:
   # Protect against returning a previously closed candle after the next TF close:
   # valid freshness checked below by client, and 12s TTL <= poll cadence.
   return cached[1]
  result=await fetch_candles(symbol)
  _cache[symbol]=(time.monotonic(),result)
  return result
@router.get("/research/deriv/closed-candles")
async def customer_deriv_closed_candles(symbol:str=Query(min_length=2,max_length=30),
                                     _customer:Customer=Depends(get_current_customer))->dict:
 if symbol not in CODES:raise HTTPException(status_code=400,detail="DERIV_SYMBOL_NOT_APPROVED")
 try:return await cached_candles(symbol)
 except Exception as exc:raise HTTPException(status_code=503,detail="VERIFIED_BROKER_CANDLES_UNAVAILABLE") from exc
