"""Align APEX TradingAgents shadow technical opinion with M5 primary scanner."""
from pathlib import Path
p=Path('/opt/apex/runtime/apex_broker_agent.py')
s=p.read_text()
backup=p.with_name(p.name+'.backup-20261031-before-M5-primary')
if not backup.exists():backup.write_text(s)
old="""    candidates=[technical[k]['trend'] for k in ('M15','H1','H4')]
    deterministic='BUY' if candidates==['UP']*3 else 'SELL' if candidates==['DOWN']*3 else 'HOLD'
    rating,narrative=('REVIEW','Model disabled for preflight.')
    if model:
        rating,narrative=run_original_agent_graph(snap,risk,symbol)
    ai_signal= 'BUY' if rating=='Buy' else 'SELL' if rating=='Sell' else 'HOLD'
    if ai_signal != deterministic:
        final='HOLD'
        reason='Agent/technical disagreement or no actionable AI rating'
    elif ai_signal=='HOLD':
        final='HOLD'
        reason='No independently confirmed agent signal'
    else:
        final=ai_signal
        reason='Shadow agreement only; NO broker orders authorized'
"""
new="""    # M5 is primary research, with higher TF alignment kept as a separate
    # context check. The LLM is never an execution authorization mechanism.
    m5=technical['M5']
    deterministic=('BUY' if m5['trend']=='UP' and m5['rsi14']>=50 else
                   'SELL' if m5['trend']=='DOWN' and m5['rsi14']<=50 else 'HOLD')
    candidates=[technical[k]['trend'] for k in ('M15','H1','H4')]
    higher_tf=('BUY' if candidates==['UP']*3 else
               'SELL' if candidates==['DOWN']*3 else 'MIXED')
    rating,narrative=('REVIEW','Model disabled for preflight.')
    if model:
        rating,narrative=run_original_agent_graph(snap,risk,symbol)
    ai_signal= 'BUY' if rating=='Buy' else 'SELL' if rating=='Sell' else 'HOLD'
    if deterministic=='HOLD':
        final='HOLD'
        reason='No confirmed M5 EMA and RSI research direction'
    elif higher_tf!=deterministic:
        final='HOLD'
        reason=f'M5 {deterministic} not aligned with M15/H1/H4 context ({higher_tf})'
    elif ai_signal!=deterministic:
        final='HOLD'
        reason=f'M5 {deterministic} not confirmed by original AI rating {rating}'
    else:
        final=ai_signal
        reason='M5/Higher timeframe/agent research agree; NO broker orders authorized'
"""
assert s.count(old)==1,('graph source changed',s.count(old))
s=s.replace(old,new,1)
old2="""            'technical_direction':deterministic,'shadow_direction':final,
"""
new2="""            'technical_direction':deterministic,'m5_direction':deterministic,
            'higher_timeframe_direction':higher_tf,'shadow_direction':final,
"""
assert s.count(old2)==1
s=s.replace(old2,new2,1)
p.write_text(s)
print('PASS original TradingAgents shadow decision now treats M5 as primary; no broker order permissions')
