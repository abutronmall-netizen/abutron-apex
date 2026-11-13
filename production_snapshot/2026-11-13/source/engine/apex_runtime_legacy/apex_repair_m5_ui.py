"""Make primary M5 visible in APEX Strategy Scanner and show truthful gate diagnoses."""
from pathlib import Path
from datetime import datetime,timezone

root=Path('/opt/apex/runtime/apex_ui')
paths=[root/'telemetry.py',root/'static'/'index.html',root/'static'/'app.js']
suffix='.backup-M5-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
for p in paths:p.with_name(p.name+suffix).write_text(p.read_text())

def exact(s,a,b):
    assert s.count(a)==1,(a[:100],s.count(a))
    return s.replace(a,b,1)

p=root/'telemetry.py';s=p.read_text()
s=exact(s,'            "m5_rsi":ind.get("M5",{}).get("rsi14"),',
'''            "m1_trend":ind.get("M1",{}).get("trend"),
            "m5_trend":ind.get("M5",{}).get("trend"),
            "m5_signal":x.get("m5_signal","HOLD"),
            "higher_tf_signal":x.get("higher_tf_signal","MIXED"),
            "m5_rsi":ind.get("M5",{}).get("rsi14"),''')
s=exact(s,'            "h4_trend":ind.get("H4",{}).get("trend"),',
'''            "h4_trend":ind.get("H4",{}).get("trend"),
            "d1_trend":ind.get("D1",{}).get("trend"),''')
p.write_text(s)

p=root/'static'/'index.html';s=p.read_text()
s=exact(s,'''<th>Family</th><th>M15</th><th>H1</th><th>H4</th><th>RSI M5</th><th>Proposal</th>''',
 '''<th>Family</th><th>M1</th><th>M5</th><th>M5 Signal</th><th>M15</th><th>H1</th><th>H4</th><th>D1</th><th>RSI M5</th><th>MTF Proposal</th>''')
s=exact(s,'<p class="table-foot">Experimental EMA/RSI logic using completed Deriv candles.',
'''<p class="table-foot">M5 is the primary research direction. M5 Signal is not a trade authorization. MTF Proposal applies higher-timeframe, RSI and instrument-family filters. Experimental EMA/RSI logic using completed Deriv candles.''')
p.write_text(s)

p=root/'static'/'app.js';s=p.read_text()
a="""return '<tr><td class="symboltext">'+esc(v.symbol)+'</td><td>'+esc(v.family)+'</td><td>'+badgeTrend(v.m15_trend)+'</td><td>'+badgeTrend(v.h1_trend)+'</td><td>'+badgeTrend(v.h4_trend)+'</td><td>'+esc(number(v.m5_rsi))+'</td><td><span class="signal '+pretty(v.proposal)+'">'+esc(v.proposal)+'</span></td><td><span class="val-down">'+esc(risk.status||"BLOCKED")+'</span></td><td>'+esc(v.reason)+'</td></tr>';"""
b="""return '<tr><td class="symboltext">'+esc(v.symbol)+'</td><td>'+esc(v.family)+'</td><td>'+badgeTrend(v.m1_trend)+'</td><td>'+badgeTrend(v.m5_trend)+'</td><td><span class="signal '+pretty(v.m5_signal)+'">'+esc(v.m5_signal||"HOLD")+'</span></td><td>'+badgeTrend(v.m15_trend)+'</td><td>'+badgeTrend(v.h1_trend)+'</td><td>'+badgeTrend(v.h4_trend)+'</td><td>'+badgeTrend(v.d1_trend)+'</td><td>'+esc(number(v.m5_rsi))+'</td><td><span class="signal '+pretty(v.proposal)+'">'+esc(v.proposal)+'</span></td><td><span class="val-down">'+esc(risk.status||"BLOCKED")+'</span></td><td>'+esc(v.reason)+'</td></tr>';"""
s=exact(s,a,b)
s=exact(s,'<tr><td colspan="9">Scanner output unavailable or unverified.</td></tr>',
 '<tr><td colspan="13">Scanner output unavailable or unverified.</td></tr>')
p.write_text(s)
print('APEX M5/M1/D1 visibility and distinct research signals patched')
