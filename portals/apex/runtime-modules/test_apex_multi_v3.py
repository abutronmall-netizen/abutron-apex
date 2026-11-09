"""Isolated APEX v3 reconciliation tests. No live broker, no order sending."""
import json,sqlite3,tempfile
from pathlib import Path
from types import SimpleNamespace as Obj
from datetime import datetime,timezone
from apex_multi_core_v3 import (
    reconcile_all,reserve_symbol,install_symbol_unique_index,ReconcileError
)
from apex_multi_gate_v3 import evaluate

MAGIC=20261031
class FakeMT5:
    POSITION_TYPE_BUY=0
    POSITION_TYPE_SELL=1
    DEAL_ENTRY_OUT=1;DEAL_ENTRY_INOUT=2;DEAL_ENTRY_OUT_BY=3
    def __init__(self):
        self.positions=[];self.orders=[];self.exits=[];self.history_works=True
    def positions_get(self):return self.positions
    def orders_get(self):return self.orders
    def history_deals_get(self,*args):return self.exits if self.history_works else None

def db():
    c=sqlite3.connect(":memory:",isolation_level=None)
    c.execute("""CREATE TABLE attempts (signal_key TEXT PRIMARY KEY,created_utc TEXT NOT NULL,
        symbol TEXT NOT NULL,side TEXT NOT NULL,state TEXT NOT NULL,request_json TEXT NOT NULL,
        broker_order INTEGER,broker_deal INTEGER,error_code TEXT)""")
    install_symbol_unique_index(c)
    return c
def makepos(ticket,symbol,volume=.05,magic=MAGIC,sl=100,tp=200,side=0):
    return Obj(ticket=ticket,symbol=symbol,magic=magic,volume=volume,sl=sl,tp=tp,type=side)
def mkrequest(vol=.05,sl=100,tp=200):
    return {"symbol":"X","volume":vol,"sl":sl,"tp":tp}
def add(c,key,symbol,ticket,state="OPEN_PROTECTED",vol=.05):
    c.execute("INSERT INTO attempts VALUES (?,?,?,?,?,?,?,?,?)",
        (key,datetime.now(timezone.utc).isoformat(),symbol,"BUY",state,
         json.dumps(mkrequest(vol)),ticket,ticket+1000,None))
def mark(c,key,state,order=None,deal=None,error=None):
    c.execute("UPDATE attempts SET state=?,broker_order=?,broker_deal=?,error_code=? WHERE signal_key=?",
       (state,order,deal,error,key))
def fail(fn,expected):
    try:fn()
    except ReconcileError as e:
        assert expected in str(e),(str(e),expected)
        return
    raise AssertionError("EXPECTED failure: "+expected)
def run():
    count=0
    def checked():
        nonlocal count
        count+=1
    t=FakeMT5();c=db()
    add(c,"k1","Volatility 75 Index.0",101)
    add(c,"k2","Crash 600 Index.0",102,.05) if False else None
    add(c,"k2","Crash 600 Index.0",102,vol=.5)
    t.positions=[makepos(101,"Volatility 75 Index.0"),makepos(102,"Crash 600 Index.0",.5)]
    got=reconcile_all(c,t,MAGIC,mark)
    assert len(got["open_apex_positions"])==2 and got["reconciled_closed"]==0;checked()
    fail(lambda:reserve_symbol(c,{"signal_key":"k3","symbol":"Crash 600 Index.0","side":"BUY"},mkrequest()),"SYMBOL_ALREADY_OPEN");checked()
    reserve_symbol(c,{"signal_key":"k3","symbol":"Volatility 10 Index.0","side":"BUY"},mkrequest())
    fail(lambda:reserve_symbol(c,{"signal_key":"k3","symbol":"Boom 600 Index.0","side":"BUY"},mkrequest()),"UNCERTAIN_BROKER_ORDER_GLOBAL_LOCK");checked()
    fail(lambda:reconcile_all(c,t,MAGIC,mark),"UNRESOLVED_BROKER_SUBMISSION");checked()
    mark(c,"k3","OPEN_PROTECTED",order=103,deal=1103)
    t.positions.append(makepos(103,"Volatility 10 Index.0"))
    assert len(reconcile_all(c,t,MAGIC,mark)["open_apex_positions"])==3;checked()
    bad=t.positions[0];t.positions[0]=makepos(101,"Volatility 75 Index.0",sl=0)
    fail(lambda:reconcile_all(c,t,MAGIC,mark),"APEX_POSITION_MISSING_SL_TP");checked()
    t.positions[0]=bad
    t.positions[0]=makepos(101,"Volatility 75 Index.0",volume=.01)
    fail(lambda:reconcile_all(c,t,MAGIC,mark),"BROKER_POSITION_TERMS_CHANGED");checked()
    t.positions[0]=bad
    t.positions.append(makepos(104,"Boom 1000 Index.0",.2))
    fail(lambda:reconcile_all(c,t,MAGIC,mark),"OFF_LEDGER_APEX_BROKER_POSITION");checked()
    t.positions.pop()
    t.positions.remove(t.positions[1])
    fail(lambda:reconcile_all(c,t,MAGIC,mark),"POSITION_MISSING_WITHOUT_FULL_CLOSE");checked()
    t.exits=[Obj(position_id=102,entry=1,volume=.1)]
    fail(lambda:reconcile_all(c,t,MAGIC,mark),"POSITION_MISSING_WITHOUT_FULL_CLOSE");checked()
    t.exits=[Obj(position_id=102,entry=1,volume=.2),Obj(position_id=102,entry=1,volume=.3)]
    got=reconcile_all(c,t,MAGIC,mark)
    assert got["reconciled_closed"]==1
    assert c.execute("SELECT state FROM attempts WHERE signal_key='k2'").fetchone()[0]=="CLOSED";checked()
    fail(lambda:reserve_symbol(c,{"signal_key":"k2","symbol":"Crash 600 Index.0","side":"BUY"},mkrequest()),"DUPLICATE_M5_SIGNAL");checked()
    reserve_symbol(c,{"signal_key":"k4","symbol":"Crash 600 Index.0","side":"BUY"},mkrequest(.5))
    mark(c,"k4","OPEN_PROTECTED",order=105,deal=1105)
    t.positions.append(makepos(105,"Crash 600 Index.0",.5))
    assert len(reconcile_all(c,t,MAGIC,mark)["open_apex_positions"])==3;checked()
    t.positions[0]=makepos(101,"Volatility 75 Index.0",magic=77)
    fail(lambda:reconcile_all(c,t,MAGIC,mark),"BROKER_POSITION_IDENTITY_MISMATCH");checked()
    t.positions[0]=bad
    t.history_works=False
    t.positions=[x for x in t.positions if x.ticket!=105]
    fail(lambda:reconcile_all(c,t,MAGIC,mark),"BROKER_CLOSE_HISTORY_UNAVAILABLE");checked()
    t.history_works=True
    # Restart recovery: persisted database and ledger without any broker submit.
    with tempfile.TemporaryDirectory() as tmp:
        path=str(Path(tmp)/"ledger.sqlite")
        disk=sqlite3.connect(path,isolation_level=None)
        c.backup(disk);disk.close()
        disk=sqlite3.connect(path,isolation_level=None)
        install_symbol_unique_index(disk)
        t.positions.append(makepos(105,"Crash 600 Index.0",.5))
        assert len(reconcile_all(disk,t,MAGIC,mark)["open_apex_positions"])==3
        fail(lambda:reserve_symbol(disk,{"signal_key":"k5","symbol":"Volatility 75 Index.0","side":"BUY"},mkrequest()),"SYMBOL_ALREADY_OPEN")
        disk.close();checked()
    # Concurrency ceiling and 13 independent symbols.
    c2=db();t2=FakeMT5()
    for i in range(13):
        add(c2,f"u{i}",f"symbol{i}",500+i,vol=1)
        t2.positions.append(makepos(500+i,f"symbol{i}",1))
    assert len(reconcile_all(c2,t2,MAGIC,mark)["open_apex_positions"])==13;checked()
    t2.positions.append(makepos(600,"symbol13",1))
    fail(lambda:reconcile_all(c2,t2,MAGIC,mark),"MORE_THAN_13_ACCOUNT_POSITIONS");checked()
    # Gate with NO account cap and already-open broker positions; fake recent source times.
    now=datetime.now(timezone.utc).isoformat()
    policy={"schema":"apex.trading.policy.v1","environment":"DERIV_DEMO",
            "live_trading":False,"automated_demo_execution":True,
            "max_demo_loss_usd":None,"max_concurrent_positions":13,"max_positions_per_symbol":1}
    broker={"schema":"apex.mt5.account.v1","source":"Deriv DEMO MT5",
            "execution_enabled":False,"live_enabled":False,"history_complete":True,
            "generated_at_utc":now,"account":{"mode":"DEMO","broker":"Deriv","currency":"USD",
            "allow_trading_account":True,"allow_trading_terminal":True,"open_positions":1},
            "positions":[{"ticket":101}]}
    from apex_fast_scanner import EXPECTED
    scanner={"schema":"apex.scanner.shadow.v1","source":"Deriv DEMO MT5",
             "orders_enabled":False,"generated_at_utc":now,
             "symbol_count":13,"instruments":[{"symbol":x,"proposal":"HOLD"} for x in EXPECTED]}
    market={"schema":"apex.mt5.market.v1","source":"Deriv DEMO MT5",
            "execution_enabled":False,"generated_at_utc":now,"data":{x:[] for x in EXPECTED}}
    d=evaluate(policy,broker,scanner,market)
    assert d["orders_allowed"] and d["account_loss_cap_usd"] is None
    assert "BROKER_EXPOSURE_PRESENT" not in d["blockers"];checked()
    policy["live_trading"]=True
    assert "DEMO_ONLY_POLICY_REQUIRED" in evaluate(policy,broker,scanner,market)["blockers"];checked()
    policy["live_trading"]=False;policy["max_demo_loss_usd"]=140
    assert "OLD_ACCOUNT_CAP_POLICY_PRESENT" in evaluate(policy,broker,scanner,market)["blockers"];checked()
    print("PASS",count,"independent unit / failure / restart / gate cases; broker order sends=0")
if __name__=="__main__":run()
