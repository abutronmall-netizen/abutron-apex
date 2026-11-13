"""Read-only, tenant-separated APEX 1.1.0 ingestion of current ABUTRON MT5 feeds.

No orders, no subscriptions, no flags, no broker account modifications. The
operator supplies none of their passwords/tokens. Measured instrument metadata
is still required for valid APEX configuration; it cannot be invented from
OHLC candles. All user LIVE accounts are excluded irrespective of config.
"""
from __future__ import annotations

import argparse
import contextlib
import io
import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path

from .bridge import AbutronApex11SignalBridge
from .candidate_contract import FP_SUPPORTED
from .production_contracts import DERIV_ALLOWED, HEX32, FeedRefused, read_deriv_native_m5
from .fp_partial_native import read_fp_partial_or_complete_m5

DB=Path('/var/lib/apex-signup/accounts.sqlite3')
FP=Path('/var/lib/abutron-fpmarkets-feed')
ROOT=Path('/var/lib/private')


def select_demo_rows(db=DB):
    """Read only broker-account metadata, not login credentials or passwords."""
    conn=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True,timeout=8)
    try:
        conn.execute('PRAGMA query_only=ON')
        rows=conn.execute('''SELECT x.id, x.account_id, x.broker,
              x.environment, x.broker_server, x.status, x.worker_binding,
              x.account_reference,COALESCE(t.desired_enabled,0),
              COALESCE(t.effective_enabled,0)
              FROM apex_mt5_connections x
              LEFT JOIN apex_trade_controls t ON t.connection_id=x.id
              WHERE x.environment='DEMO' AND x.broker IN ('Deriv','FP Markets')
              ORDER BY x.id''').fetchall()
        return rows
    finally:
        conn.close()


def load_native(row, *, now=None, historical=False, root=ROOT, fp=FP):
    cid,owner,broker,mode,server,status,worker,login,desired,effective=row
    if not isinstance(cid,str) or not HEX32.fullmatch(cid):
        raise FeedRefused('INVALID_CONNECTION_IDENTIFIER')
    if mode!='DEMO' or status!='CONNECTED' or worker!='abutron-client-mt5-'+cid:
        raise FeedRefused('DEMO_ACCOUNT_NOT_CONNECTED_TO_EXPECTED_WORKER')
    if broker=='Deriv' and server=='Deriv-Demo':
        base=root/('abutron-client-mt5-'+cid)
        health_path=base/'worker-health.json'
        try:
            h=json.loads(health_path.read_text())
        except (OSError,UnicodeError,ValueError):
            raise FeedRefused('DERIV_WORKER_HEALTH_UNREADABLE') from None
        nonce=h.get('nonce')
        if not isinstance(nonce,str) or len(nonce)!=32:
            raise FeedRefused('DERIV_NONCE_MISSING')
        folder=base/'terminal/MQL5/Files'
        sources=read_deriv_native_m5(
            connection_id=cid,health_path=health_path,
            bars_path=folder/('ABUTRON_NATIVE_BARS_V2_'+nonce+'.txt'),
            account_path=folder/('ABUTRON_NATIVE_ACCOUNT_V2_'+nonce+'.txt'),
            login=str(login),server=server,now=now,historical=historical)
    elif broker=='FP Markets' and server=='FPMarketsSC-Demo':
        live=fp/'market'/(cid+'.json')
        partial=fp/'partial'/(cid+'.json')
        src=live if live.is_file() else partial
        if not src.is_file():
            raise FeedRefused('FP_NATIVE_PUBLISHER_MARKET_OR_PARTIAL_ABSENT')
        sources=read_fp_partial_or_complete_m5(
            path=src,connection_id=cid,server=server,now=now,historical=historical)
    else:
        raise FeedRefused('BROKER_OR_SERVER_NOT_EXPLICIT_DEMO')
    if not sources:
        raise FeedRefused('NO_SUPPORTED_NATIVE_M5_SYMBOLS')
    return sources


def _manifest(path):
    try:
        value=json.loads(Path(path).read_text())
    except (OSError, ValueError):
        raise FeedRefused('MEASURED_INSTRUMENT_MANIFEST_MISSING') from None
    if isinstance(value,dict):
        if value.get('WARNING'):
            raise FeedRefused('HYPOTHETICAL_EXAMPLE_MANIFEST_NOT_ALLOWED')
        value=value.get('universe')
    if not isinstance(value,list) or not value:
        raise FeedRefused('MEASURED_MANIFEST_UNIVERSE_EMPTY')
    return value


def evaluate_native(sources,manifest):
    """One APEX engine per instrument; no other symbol's future candle enters.

    Broker *portfolio* risk remains the real native final authority, not the
    APEX starting-equity/paper portfolio model. Never write order files here.
    """
    manifests={x.get('symbol'):x for x in manifest if isinstance(x,dict)}
    if len(manifests)!=len(manifest):
        raise FeedRefused('MANIFEST_SYMBOL_DUPLICATED_OR_INVALID')
    allowed={'deriv':DERIV_ALLOWED,'fp_markets':FP_SUPPORTED}
    outcomes={}
    with tempfile.TemporaryDirectory(prefix='apex11-native-probe-') as td:
        previous=os.getcwd()
        try:
            os.chdir(td)
            Path('state').mkdir(mode=0o700)
            for symbol,src in sorted(sources.items()):
                m=manifests.get(symbol)
                if m is None:
                    continue
                if (m.get('broker')!=src.broker or symbol not in allowed[src.broker]):
                    raise FeedRefused('INSTRUMENT_MANIFEST_BROKER_MISMATCH')
                bridge=AbutronApex11SignalBridge([m])
                last=None
                for bar in src.bars:
                    last=bridge.on_closed_candle(bar)
                    if last.get('order') is not None:
                        raise FeedRefused('APEX11_SHADOW_ATTEMPTED_ORDER')
                if last is not None:
                    outcomes[symbol]={'status':last['status'],
                      'decision_id':last['decision_id'],
                      'bar_closed_ts':int(last['bar_closed_ts']),
                      'closed_bars':len(src.bars),
                      'native_source_sha256':src.source_sha256,
                      'source_kind':src.source_kind,
                      'broker_origin_independently_proven':False}
        finally:
            os.chdir(previous)
    if not outcomes:
        raise FeedRefused('NO_MEASURED_INSTRUMENTS_MATCH_LIVE_FEED')
    return outcomes


def run(*,db=DB,root=ROOT,fp=FP,manifest_path=None,historical=False,now=None):
    now=time.time() if now is None else float(now)
    manifest=_manifest(manifest_path) if manifest_path else None
    result={'schema':'abutron.apex11.mt5.readonly.probe.v1','checked_at_unix':now,
            'orders_submitted':0,'client_switches_modified':False,
            'legacy_services_modified':False,'live_trading_modified':False,
            'native_order_writes':0,'accounts':[]}
    for row in select_demo_rows(db):
        cid,owner,broker,mode,server,status,worker,login,desired,effective=row
        entry={'connection_id_suffix':cid[-4:],'broker':broker,
               'environment':mode,'server':server,
               'client_desired':desired==1,'client_effective':effective==1,
               'signal_status':'NOT_EVALUATED'}
        try:
            sources=load_native(row,now=now,historical=historical,root=root,fp=fp)
            entry['native_m5_symbols']=sorted(sources)
            entry['native_m5_closed_bar_counts']={k:len(v.bars) for k,v in sources.items()}
            if manifest is None:
                entry['signal_status']='MEASURED_INSTRUMENT_MANIFEST_REQUIRED'
            else:
                entry['signals']=evaluate_native(sources,manifest)
                entry['signal_status']='APEX11_SIGNAL_COMPUTED_NO_ORDER'
        except (FeedRefused,ValueError,KeyError,TypeError,OSError,sqlite3.Error) as exc:
            entry['signal_status']='BLOCKED_'+str(exc)[:120]
        result['accounts'].append(entry)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description='ABUTRON APEX11 DEMO feed/signal read-only inspector')
    p.add_argument('--manifest',help='broker-measured instrument metadata JSON (NOT the sample)')
    p.add_argument('--historical',action='store_true',help='offline replay only: allow old archived broker data')
    p.add_argument('--db',type=Path,default=DB)
    p.add_argument('--fp-root',type=Path,default=FP)
    p.add_argument('--worker-root',type=Path,default=ROOT)
    args=p.parse_args(argv)
    doc=run(db=args.db,root=args.worker_root,fp=args.fp_root,
            manifest_path=args.manifest,historical=args.historical)
    print(json.dumps(doc,sort_keys=True,indent=2,allow_nan=False))
    return 0

if __name__=='__main__':
    raise SystemExit(main())
