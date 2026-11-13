"""APEX Deriv MT5 account history probe. No account credentials, no trading calls."""
from datetime import datetime, timedelta, timezone
import json
import MetaTrader5 as mt5
path=r"C:\Program Files\MetaTrader 5\terminal64.exe"
if not mt5.initialize(path, timeout=12000):
    print(json.dumps({"ok":False,"reason":"terminal initialization failed"}))
else:
    try:
        info=mt5.account_info()
        if info is None or int(info.trade_mode)!=mt5.ACCOUNT_TRADE_MODE_DEMO or "deriv" not in str(info.company).lower() or "demo" not in str(info.server).lower():
            print(json.dumps({"ok":False,"reason":"not a Deriv DEMO account"}))
        else:
            end=datetime.now(timezone.utc)
            start=end-timedelta(days=30)
            deals=mt5.history_deals_get(start,end)
            if deals is None:
                print(json.dumps({"ok":False,"reason":"history query failed"}))
            else:
                rows=[d for d in deals if int(d.type) in (mt5.DEAL_TYPE_BUY,mt5.DEAL_TYPE_SELL)]
                print(json.dumps({"ok":True,"history_days":30,
                                  "broker_deal_count":len(deals),
                                  "trade_execution_count":len(rows),
                                  "closed_executions":sum(d.entry!=mt5.DEAL_ENTRY_IN for d in rows),
                                  "account_matches_Deriv_DEMO":True}))
    finally:
        mt5.shutdown()
