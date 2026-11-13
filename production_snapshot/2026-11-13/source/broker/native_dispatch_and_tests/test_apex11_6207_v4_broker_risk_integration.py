#!/usr/bin/env python3
"""Isolated QA: use broker-sized APEX sample, synthetic NO-SEND receipt
values explicitly marked TEST_ONLY. Never publish a V4 .req or CRM intent."""
import importlib.util,sys,sqlite3,json,tempfile
from pathlib import Path
from datetime import datetime,timezone
from decimal import Decimal as D
P='/var/lib/abutron-mcp/abutron-apex11-6207-existing-v4-dispatch.py'
spec=importlib.util.spec_from_file_location('apex_v4_probe_test',P)
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
from risk_guard.reservation_store import ReservationStore

def run():
    rev,nonce,eq,accounts,days,cost,sample=m.bootstrap()
    draft=json.load(open(m.STATE/'exact-order-draft-latest.json'))
    assert len(draft['drafts'])>=1
    for a in draft['drafts']:
        sym=a['symbol'];side=a['side'];order=a['order'];vol=D(order['volume'])
        tick=D(str(cost['instruments'][sym]['tick_size']))
        tickval=D(str(cost['instruments'][sym]['broker_tick_value_loss']))
        gross=abs(D(order['price'])-D(order['sl']))/tick*tickval*vol
        reward=abs(D(order['price'])-D(order['tp']))/tick*tickval*vol
        r=['']*24
        r[9]=str(order['price'])
        r[18]=str(-gross)
        r[19]=str(reward)
        r[20]='1.0'
        with sqlite3.connect('file:'+str(m.STATE/'account-bound-m5-journal.sqlite3')+'?mode=ro',uri=True) as c:
            row=c.execute('''select payload from decisions where account_id=? and symbol=? and closed_ts=?
               order by rowid desc limit 1''',
               (m.CID,sym,a['source_bar_closed_utc'])).fetchone()
        assert row is not None
        s=json.loads(row[0])
        try:
            e=m.build(a,r,s,rev,nonce,eq,accounts,days,cost,sample)
            with tempfile.TemporaryDirectory(prefix='apex-v4-QA-') as tmp:
                store=ReservationStore(Path(tmp)/'demo-qa.sqlite3')
                x=store.reserve(e.customer,e.proposal,now=datetime.now(timezone.utc))
            req=m.DemoNativeRequest(customer_id=m.OWNER,account_id=m.CID,
                broker='deriv',server='Deriv-Demo',mt5_login=m.LOGIN,
                worker_nonce=nonce,symbol=sym,side=side,
                signal_id=a['signal_id'],activation_revision=rev,
                volume_lots=order['volume'],stop_price=order['sl'],
                take_price=order['tp'],expires_at_utc=int(__import__('time').time())+12)
            port=m.RootCRMApprovedV4FilePort(account_id=m.CID,
                account_login=m.LOGIN,files_dir=m.WORK/'terminal/MQL5/Files',
                worker_uid=m.WORK.stat().st_uid)
            try:
                port.assert_ready(req,e)
                port_status='EXISTING_V4_FILE_PORT_READY_QA_NO_SEND'
            except Exception as exc:
                port_status='FILE_PORT_QA_DENIED_'+str(exc)
            print('SIMULATED_QA_ONLY',sym,side,'risk_eval',x.allowed,
                  'reason',x.reason,'reserved_volume',x.volume,'draft_volume',vol,
                  'port',port_status)
        except Exception as ex:
            print('SIMULATED_QA_ONLY',sym,side,'BUILD_ERROR',
                  type(ex).__name__,str(ex)[:150])
    print('QA_DID_NOT_QUEUE_ORDER_OR_MODIFY_CRM')
if __name__=='__main__':run()
