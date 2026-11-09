"""ABUTRONFX MT5 read-only broker handover probe; never sends orders."""
import MetaTrader5 as mt5
path=r"C:\Program Files\MetaTrader 5\terminal64.exe"
try:
 connected=mt5.initialize(path,timeout=20000)
 print("MT5_INIT",bool(connected),"ERROR_CODE",mt5.last_error()[0] if not connected else 0,flush=True)
 if connected:
  info=mt5.account_info();term=mt5.terminal_info()
  verified=bool(info and term and term.connected and info.trade_mode==mt5.ACCOUNT_TRADE_MODE_DEMO
   and "deriv" in str(info.company).lower() and "demo" in str(info.server).lower())
  print("BROKER_ACCOUNT_PRESENT",info is not None,"TERMINAL_CONNECTED",bool(term and term.connected),
        "DERIV_DEMO_VERIFIED",verified,flush=True)
  if verified:
   positions=mt5.positions_get()
   print("POSITIONS_QUERY_OK",positions is not None,"OPEN_POSITIONS",len(positions) if positions is not None else None,flush=True)
   if positions is not None:print("BROKER_NATIVE_SL_TP_PROTECTED",sum(bool(p.sl and p.tp) for p in positions),"OF",len(positions),flush=True)
finally:
 try:mt5.shutdown()
 except Exception:pass
