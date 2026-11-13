"""ABUTRON FP Markets broker-native loss and scanner decision diagnostics.
Operator read-only evidence: no broker orders, customer identifiers or risk changes.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import datetime,timezone
from pathlib import Path
import json,math,os,stat,time

HISTORY=(
  Path('/var/lib/apex/operator-live/fp-native-history.json'),
  Path('/var/lib/apex/operator-live/fp-native-history-account-80cf848587fcec6311dd93560c1c46c6.json'))
SCANNER=Path('/var/lib/abutron-fp-scanner/partial-latest.json')
AI=Path('/var/lib/abutron-fp-scanner/ai/latest.json')
QUANT=Path('/var/lib/abutron-quant-first/latest.json')
MAX_BYTES=2_000_000

def when(value):
    value=datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if value.tzinfo is None:raise ValueError('NAIVE_SOURCE_TIME')
    return value.timestamp()

def safe_read(path):
    s=path.lstat()
    if (not stat.S_ISREG(s.st_mode) or stat.S_ISLNK(s.st_mode)
        or not 100<=s.st_size<=MAX_BYTES):
        raise ValueError('FILE_UNVERIFIED')
    fd=os.open(path,os.O_RDONLY|getattr(os,'O_NOFOLLOW',0))
    try:
        a=os.fstat(fd)
        raw=os.read(fd,MAX_BYTES+1)
        b=os.fstat(fd)
    finally:os.close(fd)
    if ((a.st_ino,a.st_mtime_ns,a.st_size)!=(b.st_ino,b.st_mtime_ns,b.st_size)
        or len(raw)>MAX_BYTES):
        raise ValueError('FILE_CHANGED_DURING_READ')
    result=json.loads(raw)
    if not isinstance(result,dict):raise ValueError('NOT_OBJECT')
    return result

def valid_history(doc,now):
    if not (
        doc.get('schema')=='abutron.fpmarkets.native.account_history.readonly.v1'
        and doc.get('broker')=='FP Markets'
        and doc.get('environment')=='DEMO'
        and doc.get('available') is True
        and doc.get('history_verified_from_mt5') is True
        and doc.get('history_complete_within_selected_window') is True
        and doc.get('execution_enabled') is False
        and doc.get('orders_submitted_by_exporter')==0
        and doc.get('history_window_days')==90
        and isinstance(doc.get('account_masked'),str)
        and doc['account_masked'].startswith('••••')
        and -30<=now-when(doc['generated_at_utc'])<=180
        and -30<=now-when(doc['broker_export_at_utc'])<=180
        and isinstance(doc.get('trade_deals'),list)
        and type(doc.get('trade_deals_count')) is int
        and doc['trade_deals_count']>=0
        and type(doc.get('closing_deals_count')) is int
        and type(doc.get('open_positions_count')) is int
        and type(doc.get('pending_orders_count')) is int
        and len(doc.get('positions',[]))==doc['open_positions_count']
        and len(doc.get('pending_orders',[]))==doc['pending_orders_count']
        and isinstance(doc.get('native_file_sha256'),str)
        and len(doc['native_file_sha256'])==64):
        raise ValueError('HISTORY_SOURCE_INSUFFICIENT')
    return doc

def history_summary(doc,now):
    valid_history(doc,now)
    reported=doc['trade_deals_count']
    deals=doc['trade_deals']
    has_full_deal_detail=reported==len(deals)
    out={'account_masked':doc['account_masked'],
         'history_verified':True,
         'history_window_days':90,
         'as_of_utc':doc['broker_export_at_utc'],
         'open_positions':doc['open_positions_count'],
         'pending_orders':doc['pending_orders_count'],
         'trading_deals':reported,
         'closing_deals':doc['closing_deals_count'],
         'broker_reported_all_deal_cashflow_usd':doc.get('total_trade_deal_cashflow_usd'),
         'broker_reported_closing_cashflow_usd':doc.get('closing_deal_cashflow_usd'),
         'full_visible_deal_detail':has_full_deal_detail,
         'negative_closing_deals':None,
         'positive_closing_deals':None,
         'most_negative_symbol_cashflows':[],
         'strategy_profitability_verified':False}
    if not has_full_deal_detail:
        return out  # Native data may deliberately show only the latest 300 deals.
    aggregates=defaultdict(list)
    exits=[]
    for row in deals:
        if (not isinstance(row,dict)
            or not isinstance(row.get('symbol'),str)
            or not 1<=len(row['symbol'])<=60
            or type(row.get('net_cashflow_usd')) not in (int,float)
            or not math.isfinite(row['net_cashflow_usd'])
            or row.get('entry') not in ('IN','OUT','OUT_BY','INOUT','OTHER')):
            raise ValueError('DEAL_NOT_BROKER_VERIFIED')
        aggregates[row['symbol']].append(row)
        if row['entry'] in ('OUT','OUT_BY','INOUT'):exits.append(row)
    if len(exits)!=doc['closing_deals_count']:
        raise ValueError('EXIT_COUNT_MISMATCH')
    out['negative_closing_deals']=sum(r['net_cashflow_usd']<0 for r in exits)
    out['positive_closing_deals']=sum(r['net_cashflow_usd']>0 for r in exits)
    if out['negative_closing_deals']+out['positive_closing_deals']>len(exits):
        raise ValueError('EXIT_SIGN_COUNT_INVALID')
    rows=[{'symbol':symbol,'native_deals':len(v),
           'closing_deals':sum(x['entry'] in ('OUT','OUT_BY','INOUT') for x in v),
           'deal_cashflow_usd':round(sum(x['net_cashflow_usd'] for x in v),2)}
          for symbol,v in aggregates.items()]
    rows.sort(key=lambda r:(r['deal_cashflow_usd'],r['symbol']))
    out['most_negative_symbol_cashflows']=rows[:5]
    return out

def build(histories,scanner=None,ai=None,quant=None,now=None):
    now=time.time() if now is None else float(now)
    output={'schema':'abutron.fpmarkets.quality_diagnostics.readonly.v1',
      'checked_at_utc':datetime.fromtimestamp(now,timezone.utc).isoformat(),
      'mode':'BROKER_EVIDENCE_AND_SHADOW_RESEARCH_ONLY',
      'orders_enabled':False,'execution_authorized':False,
      'data_is_not_attributed_strategy_pnl':True,
      'account_histories':[],
      'scanner':{'available':False,'reason':'FP_SCANNER_NOT_VERIFIED'},
      'ai':{'available':False,'reason':'FP_AI_NOT_VERIFIED'},
      'quant':{'available':False,'real_order_book_verified':False,
               'out_of_sample_edge_verified':False}}
    for slot,doc in enumerate(histories):
        try:
            if slot>=2 or doc is None or doc.get('account_masked')!=('••••0512','••••1636')[slot]:
                raise ValueError('WRONG_ACCOUNT_SOURCE')
            output['account_histories'].append(history_summary(doc,now))
        except (ValueError,TypeError,KeyError,OverflowError,AttributeError):
            output['account_histories'].append({'history_verified':False,
              'reason':'BROKER_HISTORY_NOT_VERIFIED'})
    if isinstance(scanner,dict) and scanner.get('schema')=='abutron.fpmarkets.apex.scanner.partial.readonly.v1' and scanner.get('status')=='FP_SCANNER_PARTIAL_READONLY' and scanner.get('orders_enabled') is False:
        try:
            if not -30<=now-when(scanner['checked_at_utc'])<=180:
                raise ValueError('STALE_SCAN')
            rows=scanner['instruments']
            if len(rows)!=13 or not all(isinstance(r,dict) for r in rows):
                raise ValueError('INVALID_SCAN_UNIVERSE')
            counts=Counter(str(r.get('reason','UNKNOWN')) for r in rows)
            proposals=[r for r in rows if r.get('proposal') in ('BUY','SELL')]
            output['scanner']={'available':True,'symbols':13,
              'qualified_proposals':len(proposals),
              'on_hold':13-len(proposals),
              'hold_reasons':[{'reason':reason,'count':count}
                              for reason,count in counts.most_common(8)],
              'qualified_symbols':[{'symbol':r['symbol'],'direction':r['proposal']}
                                   for r in proposals],
              'checks_include':'M5 body/close, EMA9 distance, spread, price drift, M15/H1/H4 alignment',
              'orders_enabled':False}
        except (KeyError,ValueError,TypeError,OverflowError):
            pass
    if isinstance(ai,dict) and ai.get('schema')=='abutron.fpmarkets.apex.ai_selective_tradingagents.v1' and ai.get('orders_enabled') is False:
        try:
            if not -30<=now-when(ai['reviewed_at_utc'])<=480:
                raise ValueError('STALE_AI')
            reviews=ai['reviews']
            if not isinstance(reviews,list):raise ValueError('NOT_LIST')
            output['ai']={'available':True,'reviewed_candidates':len(reviews),
             'completed_reviews':sum(r.get('evidence_status')=='MODEL_REVIEW_COMPLETED' for r in reviews),
             'model_family':'Qwen / selective TradingAgents',
             'order_authority':False}
        except (KeyError,ValueError,TypeError):
            pass
    if isinstance(quant,dict) and quant.get('schema')=='abutron.apex.quant_first.shadow.v1':
        try:
            if -30<=now-when(quant['checked_at_utc'])<=300:
                output['quant']={'available':True,
                    'mode':'SHADOW_RESEARCH_ONLY',
                    'real_order_book_verified':quant.get('true_order_book_data_available') is True,
                    'out_of_sample_edge_verified':quant.get('out_of_sample_edge_verified') is True,
                    'orders_enabled':False}
        except (ValueError,KeyError,TypeError):pass
    return output

def current():
    def maybe(path):
        try:return safe_read(path)
        except (OSError,ValueError,TypeError,KeyError,UnicodeError):return None
    return build([maybe(x) for x in HISTORY],maybe(SCANNER),maybe(AI),maybe(QUANT))
