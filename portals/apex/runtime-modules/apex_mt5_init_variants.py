import MetaTrader5 as mt5
path=r"C:\Program Files\MetaTrader 5\terminal64.exe"
for label,kwargs in (
 ("EXPLICIT_PORTABLE",{"path":path,"portable":True,"timeout":18000}),
 ("DEFAULT_DISCOVERY",{"timeout":18000})
):
 try:
  ok=mt5.initialize(**kwargs)
  print(label,"OK",bool(ok),"ERR_CODE",0 if ok else mt5.last_error()[0],flush=True)
  if ok:
   info=mt5.account_info(); term=mt5.terminal_info()
   print("BROKER_SESSION_EXISTS",bool(info and term and term.connected),"BROKER_POSITION_READ_READY",bool(info and "Deriv" in str(info.company)),flush=True)
 except Exception as e:print(label,"ERROR",type(e).__name__,flush=True)
 finally:
  try:mt5.shutdown()
  except Exception:pass
