import MetaTrader5 as mt5
import time
path=r"C:\Program Files\MetaTrader 5\terminal64.exe"
for name,kw in (
    ("EXPLICIT_PATH",dict(path=path,timeout=25000)),
    ("AUTO_DISCOVERY",dict(timeout=25000))):
    started=time.time()
    try:
        ok=bool(mt5.initialize(**kw))
        err=mt5.last_error()
        print(name,"ok",ok,"error",err,"seconds",round(time.time()-started,1),flush=True)
        if ok:
            acc=mt5.account_info();terminal=mt5.terminal_info()
            print("BROKER_READ_ONLY",
                  {"has_account":acc is not None,
                   "demo":(int(acc.trade_mode)==mt5.ACCOUNT_TRADE_MODE_DEMO) if acc else None,
                   "company_deriv":("deriv" in str(acc.company).lower()) if acc else None,
                   "terminal_connected":bool(terminal.connected) if terminal else None},
                   flush=True)
            mt5.shutdown()
            break
        mt5.shutdown()
    except Exception as exc:
        print(name,"exception",type(exc).__name__,str(exc)[:150],flush=True)
