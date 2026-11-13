#!/usr/bin/env python3
"""APEX 1.1 -> existing Deriv 6207 DEMO V4 native order port.

Reads authenticated broker-native account/costs, the account-bound M5
journal, the exact native no-send OrderCheck receipt, and the existing
customer-risk sources; uses the existing root single-writer lock, risk
ReservationStore, and root-CRM V4 file port.

--probe never writes a broker request, CRM intent or risk reservation.
--dispatch reserves first, publishes at most ONE V4 file, and only reports
QUEUED. Broker ACK requires separate MT5 history evidence.
"""
from __future__ import annotations
import argparse,hashlib,importlib.util,json,math,os,re,sqlite3,sys,time
from datetime import datetime,timezone
from decimal import Decimal as D
from pathlib import Path

BASEPKG='/opt/abutron-apex11-staging/native-v4-guarded-20261108'
sys.path.insert(0, BASEPKG)
from abutron_replacement.candidate_contract import AccountGate,BrokerNativeRisk,review_candidate
from abutron_replacement.exclusive_native_writer import BrokerExecutionEvidence,DemoNativeRequest,existing_native_writer_lock
from abutron_replacement.native_v4_direct_crm_port import RootCRMApprovedV4FilePort
from abutron_replacement.native_risk_preflight import reserve_apex11_demo_candidate
from abutron_replacement.production_contracts import FeedRefused
from risk_guard.abutron_risk_guard import Account,CustomerRisk,Proposal
from risk_guard.reservation_store import ReservationStore

CID='d6fc2524ec373b8d1bc278a8be3ec635'
OWNER='4fd8991981000ffa4fa0b1c233c5195c'
LOGIN='32456207'
WORK=Path('/var/lib/private/abutron-client-mt5-'+CID)
STATE=Path('/var/lib/abutron-apex11-6207')
BROKER=Path('/var/lib/abutron-v4-broker-crm-supervisor-6207')
DB='/var/lib/apex-signup/accounts.sqlite3'
SHA='83f9ea4c23f81064a1fcdfe9c902f1a9824799d99d799e52d02e5ea3a1dec275'
AUDIT=Path('/var/lib/abutron-mcp/abutron-apex11-6207-native-ordercheck-audit-ro.py')
RESERVED=STATE/'v4-customer-risk-reservations.sqlite3'
HEX64=re.compile('^[a-f0-9]{64}$')

def stop(code):
    raise FeedRefused(code)

def source(path,age,root=True):
    if path.is_symlink():stop('SYMLINK_SOURCE')
    st=path.stat()
    if (not path.is_file() or st.st_mode&0o022 or
        (root and st.st_uid!=0) or not -3<=time.time()-st.st_mtime<=age):
        stop('SOURCE_NOT_CURRENT:'+path.name)
    return json.loads(path.read_text())

def bootstrap():
    now=int(time.time())
    with sqlite3.connect('file:'+DB+'?mode=ro',uri=True,timeout=4) as c:
        c.execute('PRAGMA query_only=on')
        row=c.execute("""
          select x.account_id,x.broker,x.environment,x.broker_server,
          x.account_reference,x.status,a.status,t.desired_enabled,
          t.effective_enabled,f.revision,f.ack_revision,f.ack_expires_utc
          from apex_mt5_connections x
          join accounts a on a.id=x.account_id
          join apex_trade_controls t on t.connection_id=x.id
          join abutron_v4_6207_activation_revision f on f.connection_id=x.id
          where x.id=?""",(CID,)).fetchone()
    if (not row or row[:7]!=(OWNER,'Deriv','DEMO','Deriv-Demo',
                              LOGIN,'CONNECTED','approved') or
        row[7:9]!=(1,1) or row[9]!=row[10] or
        type(row[11]) is not int or row[11]<now+5):
        stop('6207_CRM_EFFECTIVE_ON_OWNER_AND_ACK_UNVERIFIED')
    rev=row[9]
    h=source(WORK/'worker-health.json',20,root=False)
    nonce=h.get('nonce','')
    if (h.get('id')!=CID or h.get('broker')!='Deriv' or
        h.get('mode')!='DEMO' or h.get('server')!='Deriv-Demo' or
        h.get('status')!='CONNECTED' or h.get('heartbeat_fresh') is not True or
        not re.fullmatch('[a-f0-9]{32}',nonce)):
        stop('BROKER_DEMO_WORKER_IDENTITY_UNVERIFIED')
    ea=WORK/'terminal/MQL5/Experts/ABUTRON/AbutronApexExistingDerivV4_6207.ex5'
    if hashlib.sha256(ea.read_bytes()).hexdigest()!=SHA:
        stop('6207_V4_EA_BINARY_MISMATCH')
    proof=source(BROKER/'evidence.json',95)
    cs=proof.get('checks',{})
    if any(cs.get(k) is not True for k in (
       'apex_crm_owner_mfa_account_binding',
       'apex_enterprise_license','deriv_worker_fresh_identity',
       'deriv_independent_readonly_broker_session',
       'v4_chart_independently_attached',
       'customer_cashflow_adjusted_portfolio_risk',
       'exclusive_writer_and_unknown_orders_reconciled','client_effective_on',
       'crm_revision_fenced_and_broker_ack','live_orders_disabled')):
        stop('EXISTING_BROKER_CRM_EXPOSURE_NOT_CURRENT')
    owners=source(BROKER/'customer-wide-risk-evidence.json',95)
    ownerhash=hashlib.sha256(OWNER.encode()).hexdigest()[:12]
    o=owners.get('owners',{}).get(ownerhash,{})
    if (not o or o.get('current_open_exposure_reconciled') is not True or
        o.get('unknown_connected_broker_position_sets')!=0 or
        o.get('disconnected_or_error_accounts')!=0):
        stop('OWNER_ALL_CONNECTED_POSITIONS_UNVERIFIED')
    by_suffix={c.get('account_masked','')[-4:]:c for c in o['connections']}
    if set(by_suffix)!={'6207','0512','0178'}:
        stop('OWNER_BROKER_ACCOUNT_SET_CHANGED')
    for suffix in by_suffix:
        c=by_suffix[suffix];snap=c.get('snapshot',{})
        positions=snap.get('positions_count');pending=snap.get('pending_orders_count')
        risk=c.get('current_open_stop_risk_usd')
        if (c.get('current_open_exposure_reconciled') is not True or
            type(positions) is not int or positions<0 or
            type(pending) is not int or pending!=0 or
            type(risk) not in (int,float) or not math.isfinite(risk) or risk<0):
            stop('OWNER_BROKER_OPEN_EXPOSURE_UNVERIFIED')
        if suffix=='6207':
            if (positions>13 or
                snap.get('all_current_position_counts_verified') is not True or
                snap.get('all_current_positions_sl_tp_usd_risk_verified') is not True or
                (positions>0 and
                 c.get('broker_position_reconciliation_status')!='PROTECTED_NATIVE_DUAL_VERIFIED') or
                (positions==0 and risk!=0.0) or
                abs(D(str(snap.get('open_position_usd_stop_risk')))-D(str(risk)))>D('.01')):
                stop('DERIV_6207_BROKER_POSITION_RISK_UNVERIFIED')
        elif positions!=0 or risk!=0.0:
            stop('OTHER_OWNER_BROKER_NOT_FLAT')
    if (by_suffix['0178'].get('effective_on') is not False or
        D(str(by_suffix['0178']['snapshot']['equity_usd']))!=0):
        stop('LIVE_0178_OFF_ZERO_EQUITY_NOT_PROVEN')
    day=source(BROKER/'six-account-native-daystart-cash-audit.json',600)
    d={a['account_suffix']:a for a in day.get('accounts',[])}
    if (d.get('6207',{}).get('verified_daystart_cash_balance') is not True or
        d.get('0512',{}).get('utc_daystart_cash_balance_reconstructed_from_complete_selected_window') is not True or
        day.get('daystart_utc') != datetime.now(timezone.utc).strftime('%Y-%m-%dT00:00:00+00:00')):
        stop('BROKER_DAYSTART_CASH_UNVERIFIED')
    cost=source(BROKER/'v4-native-execution-cost-6207.json',75)
    eq=D(str(by_suffix['6207']['snapshot']['equity_usd']))
    native_eq=D(str(cost.get('account_equity_usd')))
    # Cash balance is invariant across floating-P/L ticks: require exact
    # agreement. Independently sampled equities can differ by market ticks;
    # accept only bounded drift, then use the smaller verified equity.
    if (cost.get('account_suffix')!='6207' or cost.get('worker_nonce')!=nonce or
        cost.get('native_bid_ask_and_ordercalcprofit_verified') is not True or
        cost.get('native_minlot_ordercalcmargin_verified') is not True or
        native_eq<=0 or
        abs(D(str(cost.get('account_balance_usd')))-
            D(str(by_suffix['6207']['snapshot']['balance_usd'])))>D('.01') or
        abs(native_eq-eq)>min(D('20'),eq*D('.001'))):
        stop('BROKER_COSTS_OR_EQUITY_UNVERIFIED')
    receipts=source(BROKER/'two-broker-native-order-ack-audit.json',100)
    if (receipts.get('all_existing_broker_native_order_receipts_reconciled') is not True or
        receipts.get('any_new_broker_order_unexpected_with_crm_off') is not False):
        stop('UNKNOWN_EXISTING_BROKER_ORDERS')
    obs=source(BROKER/'six-account-observed-equity.json',210)
    sample=obs['customer_owner_sampled_equity'][ownerhash]
    if (abs(D(str(sample['latest_observed_equity_usd']))-
            (eq+D(str(by_suffix['0512']['snapshot']['equity_usd']))))>D('.05') or
        sample.get('latest_observed_equity_usd') is None):
        stop('CURRENT_OWNER_EQUITY_SAMPLE_UNVERIFIED')
    return rev,nonce,min(eq,native_eq),by_suffix,d,cost,sample

def checked_candidate(nonce,eq,cost):
    draft=source(STATE/'exact-order-draft-latest.json',40)
    if draft.get('state')!='DRAFT_ONLY_NO_BROKER_ORDER_CHECK_OR_EXECUTION_AUTHORITY' or draft.get('orders_submitted')!=0:
        stop('APEX_DRAFT_SOURCE_MISMATCH')
    mod=importlib.util.spec_from_file_location('nativecheck',str(AUDIT))
    x=importlib.util.module_from_spec(mod);mod.loader.exec_module(x)
    now=int(time.time())
    for item in draft.get('drafts',[]):
        key=item.get('signal_id','')
        if (not isinstance(key,str) or not HEX64.fullmatch(key) or
            item.get('broker')!='Deriv' or item.get('environment')!='DEMO' or
            item.get('connection_id')!=CID or item.get('dispatch_authorized') is not False
            or not now+4<item.get('expires_utc',0)):
            continue
        path=WORK/'terminal/MQL5/Files/ABUTRON/execution-audit'/('apex11-check-'+key+'.txt')
        if not path.is_file() or path.is_symlink() or time.time()-path.stat().st_mtime>12:continue
        raw=path.read_text(encoding='utf-8-sig').splitlines()
        if x.verify_receipt(raw,item,nonce,now)!='NATIVE_EXACT_ORDERCHECK_PROVEN_NO_SEND':continue
        db=STATE/'account-bound-m5-journal.sqlite3'
        with sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True) as c:
            c.execute('PRAGMA query_only=on')
            rows=c.execute("""select publication_id,customer_id,payload
                from decisions where account_id=? and symbol=? and closed_ts=?
                order by rowid desc limit 1""",
                (CID,item['symbol'],item['source_bar_closed_utc'])).fetchall()
        if len(rows)!=1 or rows[0][1]!=OWNER:continue
        signal=json.loads(rows[0][2])
        side=item['side'];symbol=item['symbol']
        if (signal.get('decision_id')!=item['source_decision_id'] or
            signal.get('status')!=side or signal.get('engine')!='APEX_1_1_0' or
            signal.get('source_kind')!='deriv_native_mt5_v2' or
            signal.get('order') is not None or
            signal.get('connection_id')!=CID or
            signal.get('broker')!='deriv' or signal.get('timeframe')!='M5'):
            continue
        pubkey='|'.join((OWNER,CID,'deriv',symbol,str(int(signal['bar_closed_ts']))))
        digest=hashlib.sha256(('APEX11_M5_SHADOW|'+pubkey).encode()).hexdigest()
        if rows[0][0]!=digest:continue
        return item,raw,signal
    stop('NO_FRESH_SAME_SIGNAL_BROKER_NATIVE_ORDER_CHECK')

def build(item,receipt,signal,revision,nonce,eq,accounts,days,cost,sample):
    now=datetime.now(timezone.utc)
    o=item['order'];sym=item['symbol'];vol=D(o['volume'])
    price=D(receipt[9]);sl=D(o['sl']);tp=D(o['tp'])
    loss=-D(receipt[18]);reward=D(receipt[19]);margin=D(receipt[20])
    estimate=D(item['conservative_estimated_loss_usd'])
    budget=D(item['risk_budget_usd'])
    if (vol<=0 or loss<=0 or reward<=0 or margin<0 or
        loss>budget or estimate>budget or reward/loss<D('1.5')):
        stop('NATIVE_EXACT_ORDER_USD_RISK_REJECTED')
    spec=cost['instruments'][sym]
    tick=D(str(spec['tick_size']))
    point=D(str(spec['point']))
    tickvalue=D(str(spec['broker_tick_value_loss']))
    minstop=max(int(spec['stops_level_points']),int(spec['freeze_level_points']))
    # Conservative true broker quote, no fabricated lower slippage/fees.
    ticks=math.ceil(D(minstop)*point/tick)
    slip=math.ceil(D('15')*point/tick)
    native_stress=(abs(price-sl)/tick+D(slip))*tickvalue
    perlot_loss=loss/vol
    buffer=max(D('0.01'),estimate/vol-perlot_loss,
               native_stress-perlot_loss)
    gate=AccountGate(broker='deriv',environment='DEMO',server='Deriv-Demo',
         owner=OWNER,connection_id=CID,account_bound=True,
         worker_nonce_bound=True,fresh_broker_session=True,
         native_ea_account_match=True,broker_trade_allowed=True,
         terminal_trade_allowed=True,customer_switch_desired=True,
         customer_switch_effective=True,crm_entitlement_approved=True,
         single_writer_exclusive=True,existing_pending_orders=0,
         broker_positions_protected=True,broker_exposure_reconciled=True,
         account_equity_usd=float(eq),current_verified_stop_risk_usd=float(accounts['6207']['current_open_stop_risk_usd']),
         order_history_uncertain=False,kill_switch_halted=False,
         live_utc=int(now.timestamp()))
    native=BrokerNativeRisk(tick_size=float(tick),tick_value_per_lot_usd=float(tickvalue),
         min_lot=float(spec['min_lots']),max_lot=float(spec['max_lots']),
         lot_step=float(spec['volume_step']),min_stop_ticks=ticks,
         broker_verified=True,price=float(price),stop_price=float(sl),
         take_price=float(tp),slippage_budget_ticks=slip,
         broker_calc_profit_verified=True,broker_order_check_verified=True)
    account_rows=[]
    for suffix,cid,mode in (('6207',CID,'DEMO'),('0512','35b81a287b6a030f2f46ff426b135e6c','DEMO'),
                            ('0178','d43ff966c0c1bef5ec005fbd6ad4c0cf','LIVE')):
        c=accounts[suffix]
        ce=D(str(c['snapshot']['equity_usd']))
        base=D(str(days[suffix]['utc_daystart_reconstructed_cash_balance_usd'])) if mode=='DEMO' else D('0')
        pe=max(ce,base) if mode=='DEMO' else D('0')
        account_rows.append(Account(account_id=cid,customer_id=OWNER,
             environment=mode,equity_ccy=ce,usd_per_ccy=D('1'),
             day_start_equity_ccy=base,peak_equity_ccy=pe,
             open_stop_risk_ccy=D(str(c['current_open_stop_risk_usd'])),effective_on=c.get('effective_on') is True,
             broker_asof=now))
    customer=CustomerRisk(customer_id=OWNER,accounts=tuple(account_rows),
         day_start_equity_usd=sum((a.day_start_equity_ccy for a in account_rows),D('0')),
         peak_equity_usd=max(D(str(sample['observed_sample_high_water_usd'])),
             sum((a.peak_equity_ccy for a in account_rows),D('0'))),
         exposure_complete=True,account_inventory_complete=True)
    proposal=Proposal(customer_id=OWNER,account_id=CID,symbol=sym,
         environment='DEMO',order_side=item['side'],
         one_lot_stop_risk_ccy=perlot_loss,
         one_lot_roundtrip_cost_ccy=D('0'),
         one_lot_slippage_buffer_ccy=buffer,
         volume_min=D(str(spec['min_lots'])),volume_max=vol,
         volume_step=D(str(spec['volume_step'])),
         native_stop_validated=True,contract_spec_verified=True,
         signal_fresh=True,signal_id=item['signal_id'])
    reviewed=review_candidate(signal=signal,gate=gate,native=native,now=int(now.timestamp()))
    if (reviewed.get('engineering_gates_passed') is not True or
        reviewed.get('signal_id_for_separate_ledger')!=item['signal_id']):
        stop('EXISTING_APEX_NATIVE_REVIEW:'+','.join(reviewed.get('blockers',[]))[:120])
    if (reviewed.get('proposed_lots_research_only') is None or
        D(str(reviewed['proposed_lots_research_only']))<vol):
        stop('BROKER_NATIVE_MAX_RISK_ALLOCATION_SMALLER_THAN_DRAFT')
    evidence=BrokerExecutionEvidence(gate=gate,native=native,customer=customer,
         proposal=proposal,mt5_login=LOGIN,worker_nonce=nonce,attested_at=now,
         native_ea_protocol=4,native_ea_heartbeat_fresh=True,
         revision_fenced_by_native_ea=True,legacy_writer_same_lock_verified=True,
         outstanding_unknown_orders_reconciled=True,effective_activation_revision=revision)
    return evidence


def reconcile_existing_6207_fill(*, work=WORK, db_path=DB, store_path=RESERVED,
                                  feed_path=None, now=None):
    """Settle an already filled native V4 DEMO order; never submit an order.

    The root CRM lease and customer risk reservation are both existing ledgers.
    A broker-proven position may be reconciled with client execution OFF.
    """
    from decimal import Decimal
    from datetime import datetime, timezone
    from abutron_replacement.native_receipt_guard import (
        NativeOrderReceipt, NativePositionProof, verify_demo_broker_position)
    from risk_guard.reservation_store import ReservationStore
    from risk_guard.reservation_store import _signal_key

    now = time.time() if now is None else float(now)
    work = Path(work)
    store_path = Path(store_path)
    feed_path = (Path(feed_path) if feed_path is not None
                 else Path('/var/lib/apex-client-feed') / (CID+'.json'))
    with sqlite3.connect('file:'+str(db_path)+'?mode=ro', uri=True) as db:
        rows = db.execute("""
          SELECT di.signal_id,di.worker_nonce,di.revision,di.request_digest,
                 sl.revision,sl.request_digest,sl.status,
                 x.broker,x.environment,x.account_reference,x.broker_server,
                 x.status,x.account_id
          FROM abutron_v4_6207_direct_intents di
          JOIN abutron_v4_6207_send_lease sl ON sl.signal_id=di.signal_id
          JOIN apex_mt5_connections x ON x.id=di.account_id
          WHERE di.account_id=? AND di.state='SEND_UNKNOWN'
             AND sl.status='SEND_UNKNOWN' ORDER BY di.created_utc DESC
        """, (CID,)).fetchall()
    if not rows:
        return None
    h = source(work/'worker-health.json', 30, root=False)
    if (h.get('id')!=CID or h.get('broker')!='Deriv'
        or h.get('mode')!='DEMO' or h.get('server')!='Deriv-Demo'
        or h.get('status')!='CONNECTED' or h.get('heartbeat_fresh') is not True):
        return None
    feed = source(feed_path, 60, root=False)
    acct = feed.get('account', {})
    positions = acct.get('positions', [])
    stamp = datetime.fromisoformat(acct.get('export_mtime_utc','').replace('Z','+00:00'))
    if (feed.get('broker')!='Deriv' or feed.get('environment')!='DEMO'
        or feed.get('connection_id')!=CID or not isinstance(positions,list)
        or acct.get('open_positions')!=len(positions)
        or stamp.utcoffset() is None
        or not -2<=now-stamp.timestamp()<=60):
        return None

    folder=work/'terminal/MQL5/Files/ABUTRON'
    worker_uid=work.stat().st_uid
    def lines(rel):
        p=folder/rel
        st=p.lstat()
        if (p.is_symlink() or not p.is_file() or st.st_uid!=worker_uid
            or st.st_mode & 0o022 or st.st_size>4096 or st.st_size<20):
            raise ValueError('NATIVE_PROOF_FILE_UNTRUSTED')
        return p.read_text(encoding='utf-8-sig').splitlines()

    for sig,nonce,rev,digest,lease_rev,lease_digest,lease_status,broker,env,login,server,status,owner in rows:
        if (not HEX64.fullmatch(sig) or not re.fullmatch('[a-f0-9]{32}',nonce)
            or lease_rev!=rev or lease_digest!=digest or
            (broker,env,login,server,status)!=
            ('Deriv','DEMO',LOGIN,'Deriv-Demo','CONNECTED')
            or owner!=OWNER or h.get('nonce')!=nonce):
            continue
        try:
            r=lines(Path('receipts')/(sig+'.txt'))
            a=lines(Path('execution-audit')/(sig+'.protected.txt'))
            z=lines(Path('execution-audit')/(sig+'.result.txt'))
            if (len(r)!=10 or len(a)!=23 or len(z)<14
                or r[:4]!=['APEX_NATIVE_V2',sig,'ACK',
                           'V4_BROKER_ACK_POSITION_STILL_UNVERIFIED']
                or r[7:]!=[nonce,LOGIN,'Deriv-Demo']
                or a[:5]!=['ABUTRON_NATIVE_PROTECTED_AUDIT_V1',sig,nonce,LOGIN,'Deriv-Demo']
                or a[22]!='OPEN_PROTECTED'
                or z[:5]!=['ABUTRON_NATIVE_RESULT_AUDIT_V1',sig,nonce,LOGIN,'Deriv-Demo']
                or z[10]!='10009'
                or (a[7],a[8])!=(r[4],r[5])
                or (z[12],z[13])!=(r[4],r[5])
                or a[9]!=a[7]):
                continue
            candidates=[p for p in positions if
                        (str(p.get('ticket'))==a[9]
                         and p.get('symbol')==a[5]
                         and p.get('side')==a[6]
                         and Decimal(str(p.get('volume')))==Decimal(a[10])
                         and Decimal(str(p.get('open_price')))==Decimal(a[11])
                         and Decimal(str(p.get('sl')))==Decimal(a[14])
                         and Decimal(str(p.get('tp')))==Decimal(a[15])
                         and p.get('protected') is True)]
            if len(candidates)!=1:
                continue
            store=ReservationStore(store_path)
            filled=Decimal(a[10])
            with sqlite3.connect('file:'+str(store_path)+'?mode=ro',uri=True) as rc:
                risk_row=rc.execute(
                  'SELECT customer_id,account_id,state,volume,broker_proof_ref '
                  'FROM intents WHERE signal_key=?', (_signal_key(CID,sig),)).fetchone()
            if (not risk_row or risk_row[0]!=OWNER or risk_row[1]!=CID
                or risk_row[2] not in ('RESERVED','UNKNOWN','RECONCILED')
                or filled!=Decimal(risk_row[3])):
                continue
            bt=datetime.fromtimestamp(int(r[6]),timezone.utc)
            pt=datetime.fromtimestamp(int(a[21]),timezone.utc)
            native=NativeOrderReceipt(broker='deriv',environment='DEMO',
                   server='Deriv-Demo',account_id=CID,signal_id=sig,
                   symbol=a[5],side=a[6],broker_return_code=10009,
                   order_id=r[4],deal_id=r[5],position_id=a[9],
                   volume_lots=filled,broker_time=bt)
            pos=NativePositionProof(account_id=CID,server='Deriv-Demo',
                   position_id=a[9],symbol=a[5],side=a[6],
                   volume_lots=filled,open_price=Decimal(a[11]),
                   stop_loss=Decimal(a[14]),take_profit=Decimal(a[15]),
                   broker_snapshot_time=pt,in_reconciled_open_exposure=True,
                   pending_remainder_or_unknown_order=False)
            proof=verify_demo_broker_position(receipt=native,position=pos,
                    expected_account_id=CID,expected_signal_id=sig,
                    expected_symbol=a[5],expected_side=a[6],
                    reserved_lots=filled,trusted_native_worker_verified=True)
            # The identical full fill is visible in the current native account
            # snapshot. No change to CRM switch state, activation revision or EA.
            if risk_row[2]=='RECONCILED':
                store.require_finalized_broker_proof(customer_id=OWNER,
                      account_id=CID,signal_id=sig,
                      outcome='PROTECTED_POSITION',proof_ref=proof)
            else:
                store.complete(CID,sig,outcome='RECONCILED',broker_proof=proof,
                               now=pt,reconciled_snapshot_includes_position=True)
            with sqlite3.connect(str(db_path), timeout=10,isolation_level=None) as db:
                db.execute('BEGIN IMMEDIATE')
                try:
                    n=int(now)
                    changed=db.execute("""
                      UPDATE abutron_v4_6207_send_lease
                      SET status='RECONCILED',updated_utc=?
                      WHERE signal_id=? AND revision=? AND request_digest=?
                        AND status='SEND_UNKNOWN'
                    """,(n,sig,rev,digest)).rowcount
                    if changed!=1:
                        raise ValueError('CRM_LEASE_NO_LONGER_UNKNOWN')
                    db.execute("""
                      INSERT INTO apex_trade_control_audit
                      (account_id,connection_id,requested_enabled,outcome,occurred_at)
                      VALUES(?,?,?,?,?)
                    """,(OWNER,CID,1,'APEX11_6207_BROKER_FILL_RECONCILED',n))
                    db.execute('COMMIT')
                except BaseException:
                    db.execute('ROLLBACK')
                    raise
            return dict(state='BROKER_FILL_RECONCILED_EXISTING_LEDGERS',
                        broker_order=r[4],broker_deal=r[5],
                        symbol=a[5],side=a[6],lots=str(filled),
                        crm_revision_at_order=rev,risk_proof=proof,
                        orders_submitted=0,live_enabled=False)
        except (OSError,ValueError,TypeError,IndexError,KeyError,
                sqlite3.Error):
            continue
    return None


def run(should_dispatch:bool):
    if os.geteuid()!=0:stop('ROOT_WRITER_REQUIRED')
    with existing_native_writer_lock():
        if should_dispatch:
            settled=reconcile_existing_6207_fill()
            if settled:
                print(json.dumps(settled))
                return
        revision,nonce,eq,accounts,days,cost,sample=bootstrap()
        item,receipt,signal=checked_candidate(nonce,eq,cost)
        evidence=build(item,receipt,signal,revision,nonce,eq,accounts,days,cost,sample)
        o=item['order']
        req=DemoNativeRequest(customer_id=OWNER,account_id=CID,broker='deriv',
              server='Deriv-Demo',mt5_login=LOGIN,worker_nonce=nonce,
              symbol=item['symbol'],side=item['side'],signal_id=item['signal_id'],
              activation_revision=revision,volume_lots=o['volume'],
              stop_price=o['sl'],take_price=o['tp'],
              expires_at_utc=int(time.time())+11)
        port=RootCRMApprovedV4FilePort(account_id=CID,account_login=LOGIN,
              files_dir=WORK/'terminal/MQL5/Files',worker_uid=WORK.stat().st_uid)
        port.assert_ready(req,evidence)
        if not should_dispatch:
            print(json.dumps(dict(state='EXACT_APEX_V4_READY_NO_SEND',symbol=req.symbol,
                 side=req.side,lots=req.volume_lots,crm_revision=revision,
                 native_ordercheck_retcode=int(receipt[16]),broker_order_ack=False,
                 orders_submitted=0)))
            return
        store=ReservationStore(RESERVED)
        result=reserve_apex11_demo_candidate(signal=signal,gate=evidence.gate,
             native=evidence.native,customer=evidence.customer,
             proposal=evidence.proposal,store=store,now=datetime.now(timezone.utc))
        if not result.risk_reserved or result.reserved_volume!=D(req.volume_lots):
            stop('EXISTING_RISK_RESERVATION_DENIED:'+result.reason)
        # Reservation held before immutable native queue; unknown outcomes
        # remain held. Never retry this signal after any dispatch attempt.
        store.mark_unknown(CID,req.signal_id)
        port.queue_once(req,evidence)
        print(json.dumps(dict(state='V4_NATIVE_REQUEST_QUEUED_AWAITING_BROKER',
             symbol=req.symbol,side=req.side,lots=req.volume_lots,
             crm_revision=revision,signal_id=req.signal_id,orders_confirmed=0,
             broker_order_ack=False,live_enabled=False)))

if __name__=='__main__':
    p=argparse.ArgumentParser()
    m=p.add_mutually_exclusive_group(required=True)
    m.add_argument('--probe',action='store_true')
    m.add_argument('--dispatch',action='store_true')
    args=p.parse_args()
    try:run(args.dispatch)
    except Exception as ex:
        print(json.dumps(dict(state='NO_NEW_APEX_NATIVE_ORDER_REQUEST',
             reason=type(ex).__name__+':'+str(ex)[:180],
             orders_confirmed=0,broker_order_ack=False,live_enabled=False)))
        # A missing fresh signal is normal between M5 bars, not a service failure.
        if args.dispatch and not any(str(ex).startswith(x) for x in (
            'NO_FRESH_SAME_SIGNAL_BROKER_NATIVE_ORDER_CHECK',
            'EXCLUSIVE_NATIVE_WRITER_BUSY',
            'SIGNAL_ALREADY_RESERVED_OR_PROCESSED')):
            sys.exit(2)
