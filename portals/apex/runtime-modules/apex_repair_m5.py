"""Correct scanner diagnosis; preserve unvalidated-strategy execution lock."""
from pathlib import Path
p=Path('/opt/apex/runtime/apex_fast_scanner.py')
original=p.read_text()
backup=p.with_name(p.name+'.backup-20261031-before-M5-diagnostics')
if not backup.exists():backup.write_text(original)
old='''    reason="No aligned M15/H1/H4 trend"
    proposal="HOLD"
    if alignment==("UP",)*3 and m5["trend"]=="UP" and 53<=m5["rsi14"]<=70 and m5["atr14"]>0:
        proposal="BUY";reason="EMA9>EMA21 and RSI supports higher-timeframe uptrend"
    elif alignment==("DOWN",)*3 and m5["trend"]=="DOWN" and 30<=m5["rsi14"]<=47 and m5["atr14"]>0:
        proposal="SELL";reason="EMA9<EMA21 and RSI supports higher-timeframe downtrend"
    if proposal!="HOLD" and family in ("Crash","Boom"):
        # Do not assume generic trend-following profits from broker-simulated spikes.
        proposal="HOLD";reason="Crash/Boom family blocked pending separate spike-model certification"
    return {
        "symbol":symbol,"family":family,"proposal":proposal,"reason":reason,
        "last_closed_m5":m5["bar_time"],"source":"Deriv MT5 completed candles",
        "indicators":indicators,
        "execution_authorized":False,"trade_ready":False,
        "risk_status":"NOT_CERTIFIED",
        "strategy":"apex_ema_rsi_mtf_research_v1",
    }'''
new='''    # M5 is the *primary* directional research timeframe. Higher TFs are
    # separate confirmation filters; a veto is not evidence that M5 has no signal.
    m5_signal={"UP":"BUY","DOWN":"SELL"}.get(m5["trend"],"HOLD")
    htf_signal="BUY" if alignment==("UP",)*3 else "SELL" if alignment==("DOWN",)*3 else "MIXED"
    proposal="HOLD"
    if m5_signal=="HOLD":
        reason=(f"M5 mixed: EMA9/EMA21 + RSI14={m5['rsi14']:.2f} do not confirm direction; "
                f"M15/H1/H4={alignment[0]}/{alignment[1]}/{alignment[2]}")
    elif htf_signal=="MIXED":
        reason=(f"M5 research {m5_signal}; higher TF conflict: "
                f"M15/H1/H4={alignment[0]}/{alignment[1]}/{alignment[2]}")
    elif m5_signal!=htf_signal:
        reason=f"M5 {m5_signal} conflicts with aligned M15/H1/H4 {htf_signal}"
    elif m5["atr14"]<=0:
        reason="M5 ATR unavailable: research setup not validated"
    elif m5_signal=="BUY" and not 53<=m5["rsi14"]<=70:
        reason=f"M5 BUY direction aligned but RSI14={m5['rsi14']:.2f} outside 53–70 entry filter"
    elif m5_signal=="SELL" and not 30<=m5["rsi14"]<=47:
        reason=f"M5 SELL direction aligned but RSI14={m5['rsi14']:.2f} outside 30–47 entry filter"
    elif family in ("Crash","Boom"):
        reason=f"M5 {m5_signal} confirmed; {family} spike-model requires separate testing"
    else:
        proposal=m5_signal
        reason=f"M5 {m5_signal} research aligned with M15/H1/H4 and RSI14 filter"
    return {
        "symbol":symbol,"family":family,"proposal":proposal,"reason":reason,
        "m5_signal":m5_signal,"higher_tf_signal":htf_signal,
        "m5_confirmation":m5_signal!="HOLD" and m5_signal==htf_signal,
        "last_closed_m5":m5["bar_time"],"source":"Deriv MT5 completed candles",
        "indicators":indicators,
        "execution_authorized":False,"trade_ready":False,
        "risk_status":"NOT_CERTIFIED",
        "strategy":"apex_ema_rsi_mtf_research_v1",
    }'''
assert original.count(old)==1, f'unexpected scanner source {original.count(old)}'
p.write_text(original.replace(old,new,1))
print('M5 diagnostics source repaired; original backup',backup)
