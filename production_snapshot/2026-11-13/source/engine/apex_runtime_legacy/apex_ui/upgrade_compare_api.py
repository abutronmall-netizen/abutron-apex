"""APEX eight-frame comparison routes and scanner source annotations."""
from pathlib import Path
from datetime import datetime,timezone

src=Path("/opt/apex/runtime/apex_ui")
paths=[src/"app.py",src/"telemetry.py"]
stamp=".backup-eightframe-"+datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
for f in paths:f.with_name(f.name+stamp).write_text(f.read_text())

def repl(text,old,new):
    count=text.count(old)
    if count!=1:raise ValueError("Unexpected app source layout "+old[:90]+" count "+str(count))
    return text.replace(old,new,1)

p=src/"app.py";s=p.read_text()
s=repl(s,'from apex_ui.telemetry import broker_account, scanner_status, governor_status, broker_prechecks, execution_preview',
'''from apex_ui.telemetry import broker_account, scanner_status, governor_status, broker_prechecks, execution_preview
from apex_ui.candle_compare import compare as compare_completed_candles''')
s=repl(s,'@app.get("/api/chart")','''@app.get("/api/candle-comparison")
def comparison(symbol: str = Query(..., min_length=3, max_length=80)):
    try:
        return JSONResponse(compare_completed_candles(symbol))
    except ValueError as ex:
        # Broker-source, closed-bar and age checks are required.
        if "approved Deriv" in str(ex):
            raise HTTPException(status_code=404,detail="Unknown broker symbol")
        raise HTTPException(status_code=503,detail="Broker candles unavailable or unverified")


@app.get("/api/chart")''')
p.write_text(s)
p=src/"telemetry.py";s=p.read_text()
s=repl(s,'''    t=age(doc.get("generated_at_utc"))
    instruments=[]
    for x in doc.get("instruments",[])[:13]:''','''    t=age(doc.get("generated_at_utc"))
    # For a matching completed M5 bar, expose its single-candle close/open
    # bias independently of the scanner's multi-candle EMA/RSI direction.
    broker=read(Path("/var/lib/apex/mt5-market/deriv_demo_bars.json"))
    broker_data={}
    if (broker and broker.get("schema")=="apex.mt5.market.v1"
        and broker.get("source")=="Deriv DEMO MT5"
        and broker.get("execution_enabled") is False):
        broker_age=age(broker.get("generated_at_utc"))
        if broker_age is not None and broker_age<=660:
            broker_data=broker.get("data",{})
    instruments=[]
    for x in doc.get("instruments",[])[:13]:''')
s=repl(s,'''        ind=x.get("indicators",{})
        instruments.append({''','''        ind=x.get("indicators",{})
        frame=broker_data.get(x.get("symbol"),{}).get("M5",[])
        bar=frame[-1] if frame else None
        if bar and bar.get("time")==x.get("last_closed_m5"):
            candle_bias=("BUY" if bar["close"]>bar["open"] else
                         "SELL" if bar["close"]<bar["open"] else "NEUTRAL")
            candle_closed=datetime.fromtimestamp(int(bar["time"])+300,timezone.utc).isoformat()
        else:
            candle_bias="UNAVAILABLE"
            candle_closed=None
        instruments.append({''')
s=repl(s,'''            "m5_signal":x.get("m5_signal","HOLD"),''','''            "m5_signal":x.get("m5_signal","HOLD"),
            "m5_candle_bias":candle_bias,
            "m5_candle_closed_utc":candle_closed,''')
p.write_text(s)
print("APEX UI server eight-frame comparison API + scanner candle bias ready")
