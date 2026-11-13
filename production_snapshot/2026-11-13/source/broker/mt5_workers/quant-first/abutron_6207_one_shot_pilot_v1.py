#!/usr/bin/env python3
"""6207-only DEMO prospective research publication and one-shot pilot.
No strategy profitability claim. Never enables another account or LIVE trading.
CLI --publish (no orders); --inspect (no orders); --dispatch (explicit root approval).
"""
from __future__ import annotations
import argparse,datetime as dt,fcntl,hashlib,json,math,os,re,sqlite3,stat,sys,tempfile,time
from pathlib import Path
sys.path[:0]=['/opt/apex-client-mt5','/opt/apex-client-portal','/opt/apex-signup','/opt/apex-client-mt5/quant-first']
import customer_order_ledger as ledger
import apex_native_order_runtime as native
import apex_signal_native_router_v1 as router
from apex_portfolio_guard_v3 import capacity,UnsafeExposure
from abutron_entry_quality_guard_v1 import eligibility as quality_eligibility

ROOT=Path('/var/lib/abutron-6207-pilot')
SOURCE=Path('/var/lib/abutron-quant-first')
DB=SOURCE/'entry-model-causal-v2.sqlite3'
PUBLISHED=ROOT/'research-intent-v1.json'
AUDIT=ROOT/'pilot-result-v1.json'
APPROVAL=Path('/etc/abutron/6207-pilot-approval.json')
MODEL=Path('/opt/apex-client-mt5/quant-first/abutron_entry_model_v1.py')
COST=Path('/var/backups/abutron-cost-research-20261106T2235Z/BROKER_COST_REFERENCE_EQUITY_V2.json')
ALLOWED={'Volatility 25 Index.0','Volatility 50 Index.0','Volatility 75 Index.0'}
SCHEMA='abutron.6207.research_native_intent.v1'
CID='d6fc2524ec373b8d1bc278a8be3ec635'
MAX_PUBLISH_WAIT=310
MAX_ENTRY_LATENCY=12
class Denied(RuntimeError):pass

def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def read(path,limit=4000000):
    if path.is_symlink() or not path.is_file() or not 0<path.stat().st_size<=limit:raise Denied('SOURCE_MISSING_OR_UNTRUSTED')
    return json.loads(path.read_text())
def stamp(value):
    t=dt.datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if t.tzinfo is None:raise Denied('TIMESTAMP_NAIVE')
    return t.timestamp()
def atomic_json(path,payload):
    path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if path.is_symlink():raise Denied('OUTPUT_SYMLINK')
    fd,tmp=tempfile.mkstemp(prefix='.6207-',dir=path.parent)
    try:
        with os.fdopen(fd,'w') as out:
            json.dump(payload,out,indent=2,allow_nan=False);out.write('\n');out.flush();os.fsync(out.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)
def identity():
    rows=[r for r in router.account_rows() if r[0]==CID]
    if len(rows)!=1:raise Denied('6207_ACCOUNT_MISSING_OR_DUPLICATE')
    r=rows[0]
    if r[2:6]!=('Deriv','DEMO','Deriv-Demo','CONNECTED') or not str(r[7]).endswith('6207'):
        raise Denied('6207_NOT_DERIV_DEMO_CONNECTED')
    if not native.optionc_on(CID):raise Denied('6207_ADAPTIVE_POLICY_NOT_ACTIVE')
    return r
def valid_observation(row,now,modelhash,costhash):
    sym,model,bar,first,lag,entry,side,barhash,mhash,chash,status=row
    if sym not in ALLOWED or side not in ('BUY','SELL') or status!='WAITING_FOR_GENUINELY_FUTURE_ENTRY':
        return False
    if quality_eligibility(sym,model,side)[0] is not True:
        return False
    if not isinstance(entry,int) or not isinstance(bar,int) or entry%300:
        return False
    if not isinstance(barhash,str) or re.fullmatch('[a-f0-9]{64}',barhash) is None:
        return False
    if mhash!=modelhash or chash!=costhash:return False
    try:observed=stamp(first)
    except (ValueError,TypeError,Denied):return False
    if not (0<=lag<=180 and bar+300<=observed<entry and 0<entry-observed<=300):
        return False
    if not -MAX_ENTRY_LATENCY<=entry-now<=MAX_PUBLISH_WAIT:return False
    return True
def observed_candidate_rows(now,modelhash,costhash):
    with sqlite3.connect('file:'+str(DB)+'?mode=ro',uri=True,timeout=5) as c:
        c.execute('PRAGMA query_only=ON')
        if c.execute('PRAGMA quick_check').fetchone()[0]!='ok':raise Denied('FORWARD_DB_CORRUPT')
        rows=c.execute("""SELECT symbol,model,signal_m5_start,first_observed_utc,
         signal_age_sec,planned_entry_m5_start,side,signal_bar_hash,model_sha256,
         cost_sha256,status FROM observed WHERE status='WAITING_FOR_GENUINELY_FUTURE_ENTRY'
         AND planned_entry_m5_start BETWEEN ? AND ? ORDER BY planned_entry_m5_start,symbol,model""",
         (int(now-MAX_ENTRY_LATENCY),int(now+MAX_PUBLISH_WAIT))).fetchall()
    return [r for r in rows if valid_observation(r,now,modelhash,costhash)]
def source_ok(now):
    forward=read(SOURCE/'entry-model-causal-v2-latest.json')
    if forward.get('schema')!='abutron.quant.causal_forward_market_outcome.v2':
        raise Denied('FORWARD_SCHEMA_MISMATCH')
    if not -15<=now-stamp(forward.get('checked_at_utc'))<=150:raise Denied('FORWARD_REPORT_STALE')
    mh=hashlib.sha256(MODEL.read_bytes()).hexdigest()
    ch=hashlib.sha256(COST.read_bytes()).hexdigest()
    if forward.get('strategy_model_sha256')!=mh or forward.get('cost_model_sha256')!=ch:
        raise Denied('STRATEGY_OR_COST_SOURCE_DRIFT')
    return mh,ch
def publish(now=None):
    now=time.time() if now is None else float(now)
    status={'schema':SCHEMA,'created_at_utc':dt.datetime.fromtimestamp(now,dt.timezone.utc).isoformat(),
     'account_suffix':'6207','mode':'RESEARCH_INTENT_ONLY_NO_ORDER_AUTHORITY','candidates':[],
     'order_submission_allowed':False,'orders_sent':0,'blockers':[],
     'quality_quarantine_policy':'abutron.entry_quality_guard.v1',
     'weak_setup_quarantine_count':2}
    try:
        row=identity();owner=row[1];mh,ch=source_ok(now)
        candidates=observed_candidate_rows(now,mh,ch)
        grouped={}
        for sym,model,bar,first,lag,entry,side,barhash,*_ in candidates:
            grouped.setdefault((sym,entry),[]).append((model,side,bar,first,barhash))
        for (sym,entry),v in sorted(grouped.items(),key=lambda x:(x[0][1],x[0][0])):
            if len(set(x[1] for x in v))!=1:continue  # Never dispatch conflicting strategies.
            model,side,bar,first,barhash=sorted(v)[0]
            ledgerbar=entry-300
            key=ledger.expected_key(owner,CID,sym,ledgerbar,side)
            status['candidates'].append({'account_suffix':'6207','symbol':sym,
              'model':model,'side':side,'source_signal_m5_start':bar,
              'source_observed_at_utc':first,'source_bar_sha256':barhash,
              'planned_entry_m5_start':entry,'ledger_m5_bar_time':ledgerbar,
              'signal_key':key,'strategy_sha256':mh,'cost_sha256':ch,
              'order_submission_allowed':False})
        status['blockers']=['PUBLICATION_IS_NOT_ORDER_APPROVAL','PILOT_REQUIRES_EXPLICIT_LIVE_GATES']
    except (Denied,ValueError,TypeError,sqlite3.Error,OSError) as e:
        status['blockers']=['FAIL_CLOSED_'+str(e)[:150]]
    atomic_json(PUBLISHED,status)
    print('6207_RESEARCH_PUBLISHED',len(status['candidates']),'NO_BROKER_ORDERS',status['blockers'][0])
    return status

def authorize_6207(now):
    if APPROVAL.is_symlink() or not APPROVAL.is_file():raise Denied('EXPLICIT_PILOT_APPROVAL_FILE_ABSENT')
    st=APPROVAL.stat()
    if st.st_uid!=0 or (stat.S_IMODE(st.st_mode)&0o077):raise Denied('PILOT_APPROVAL_FILE_PERMISSIONS_INVALID')
    p=read(APPROVAL,4096)
    if (p.get('schema')!='abutron.6207.one_shot_pilot_approval.v1' or
      p.get('account_suffix')!='6207' or p.get('demo_only') is not True or
      p.get('engineering_pilot_only') is not True or p.get('max_orders')!=1 or
      p.get('risk_percent')!=0.10 or p.get('portfolio_ceiling_percent')!=20 or
      p.get('authorized') is not True):
        raise Denied('PILOT_APPROVAL_POLICY_INVALID')
    if not stamp(p.get('not_before_utc'))<=now<stamp(p.get('expires_at_utc')):
        raise Denied('PILOT_AUTHORIZATION_OUTSIDE_WINDOW')
    return p

def fresh_runtime_checks(now):
    row=identity()
    if row[8]!=1 or row[9]!=1:raise Denied('6207_EFFECTIVE_AUTO_SWITCH_OFF')
    handover=router.read(router.HANDOVER)
    if handover.get('status')!='APPROVED_FOR_TRADING_CUTOVER':
        # Dedicated DEMO-only exception does not enable the global dispatcher.
        # Requires an independently fresh, private 6207-only native cutover
        # lease plus the customer's effective ON acknowledgement.
        sys.path.insert(0,'/opt/apex-client-mt5/execution-fix')
        from abutron_6207_cutover_v1 import delegation_active
        if not delegation_active(CID,row[1],row[8]):
            raise Denied('EXCLUSIVE_6207_CUTOVER_NOT_APPROVED')
    if not router.manager.attest(CID,'Deriv','Deriv-Demo'):raise Denied('BROKER_SESSION_NOT_ATTESTED')
    from apex_customer_worker_entitlement import evaluate
    with sqlite3.connect('file:'+router.DB+'?mode=ro',uri=True,timeout=6) as conn:
        allowed,reason,_=evaluate(conn,{'account_id':row[1],'connection_id':CID,'broker':'Deriv',
          'platform':'MT5','environment':'DEMO','account_reference':row[7],
          'broker_server':'Deriv-Demo','worker_binding':row[6]})
    if not allowed:raise Denied('CRM_LICENSE_DENIED_'+str(reason)[:50])
    ea,err=native.ea_state_v2(CID,row[7],row[4])
    if err or not ea or ea.get('protocol_version')!=3 or not ea.get('native_demo_orders_enabled'):
        raise Denied('6207_NATIVE_EA_V3_NOT_READY')
    if not ea.get('terminal_trade_allowed') or not ea.get('account_trade_allowed'):
        raise Denied('TERMINAL_OR_BROKER_TRADING_DISABLED')
    native.verify_6207_audit_readiness(ea['files'],ea['nonce'],row[7],row[4])
    account=native.fresh_customer_broker_feed(CID,row[1])
    occupied=capacity(CID,account,ea,row[7],row[4],ledger.SYMBOLS,ledger.DB)
    if occupied or ea['positions']!=0 or ea['pending_orders']!=0 or account['positions']:
        raise Denied('6207_PILOT_ACCOUNT_NOT_FLAT_OR_PENDING')
    equity=account['equity_usd']
    if not isinstance(equity,(int,float)) or not math.isfinite(equity) or equity<=0:
        raise Denied('BROKER_EQUITY_INVALID')
    if .001*equity>.2*equity:raise Denied('RISK_CEILING_CONFLICT')
    with sqlite3.connect('file:'+str(ledger.DB)+'?mode=ro',uri=True) as c:
        active=c.execute("""SELECT count(*) FROM attempts WHERE connection_id=? AND state IN
          ('RESERVED','SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED','OPEN_PROTECTED','UNPROTECTED')""",(CID,)).fetchone()[0]
    if active:raise Denied('6207_LEDGER_UNRECONCILED')
    return row,ea,account

def choose_published(now):
    pub=read(PUBLISHED,100000)
    if pub.get('schema')!=SCHEMA or pub.get('account_suffix')!='6207':
        raise Denied('PUBLISHED_INTENT_ACCOUNT_OR_SCHEMA_INVALID')
    if not 0<=now-stamp(pub['created_at_utc'])<=80:raise Denied('PUBLISHED_INTENT_STALE')
    mh,ch=source_ok(now)
    valid=observed_candidate_rows(now,mh,ch)
    pubrows=pub.get('candidates',[])
    due=[]
    for r in valid:
        sym,model,bar,first,lag,entry,side,barhash,*_=r
        if not entry<=now<entry+MAX_ENTRY_LATENCY:continue
        matched=[p for p in pubrows if p.get('symbol')==sym and p.get('model')==model and
             p.get('source_signal_m5_start')==bar and p.get('planned_entry_m5_start')==entry and
             p.get('side')==side and p.get('source_bar_sha256')==barhash and
             p.get('strategy_sha256')==mh and p.get('cost_sha256')==ch]
        if len(matched)!=1:continue
        if sum(x[0]==sym and x[5]==entry and x[6]!=side for x in valid):continue
        due.append(matched[0])
    if not due:raise Denied('NO_PRECOMMITTED_FRESH_RESEARCH_SIGNAL')
    due.sort(key=lambda p:(p['planned_entry_m5_start'],p['symbol'],p['model']))
    return due[0]

def one_shot_dispatch():
    if os.geteuid()!=0:raise Denied('ROOT_REQUIRED')
    ROOT.mkdir(mode=0o700,parents=True,exist_ok=True)
    lockpath=native.ROOT/'execution-writer.lock'
    lockpath.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    fd=os.open(lockpath,os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        now=time.time()
        authorize_6207(now)
        marker=ROOT/'ONE_SHOT_CONSUMED'
        if marker.exists() or marker.is_symlink():raise Denied('6207_PILOT_ALREADY_CONSUMED_NO_RETRY')
        row,ea,account=fresh_runtime_checks(now)
        cand=choose_published(time.time())
        if cand['symbol'] not in ALLOWED:raise Denied('SYMBOL_SCOPE_INVALID')
        # Key equals existing durable native-order ledger identity for the planned M5.
        k=ledger.expected_key(row[1],CID,cand['symbol'],cand['ledger_m5_bar_time'],cand['side'])
        if k!=cand['signal_key']:raise Denied('RESEARCH_TO_LEDGER_IDENTITY_MISMATCH')
        folder=ea['files']/'ABUTRON'
        if folder.is_symlink() or not folder.is_dir() or (folder/native.REQUEST_NAME).exists():
            raise Denied('PENDING_NATIVE_ORDER_OR_UNTRUSTED_FOLDER')
        if (folder/native.RECEIPT_DIR/(k+'.txt')).exists():raise Denied('BROKER_RECEIPT_ALREADY_EXISTS')
        if time.time()>=cand['planned_entry_m5_start']+MAX_ENTRY_LATENCY:
            raise Denied('NEW_ENTRY_WINDOW_EXPIRED')
        # Permanently consume one-shot authorization BEFORE any broker-visible change.
        mf=os.open(marker,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(mf,'w') as f:
            f.write(utc()+' '+k[:12]+'\n');f.flush();os.fsync(f.fileno())
        dfd=os.open(ROOT,os.O_RDONLY|os.O_DIRECTORY)
        try:os.fsync(dfd)
        finally:os.close(dfd)
        proof={'broker':'Deriv','environment':'DEMO','server':'Deriv-Demo',
          'current_broker_identity_verified':True,'open_positions':0,'occupied_symbols':[],
          'protected_positions_reconciled':True,'pending_orders':0,
          'risk_governor_approved':True,'account_trade_authorized':True,
          'single_writer_approved':True}
        with ledger.new() as c:
            ledger.reserve(c,row[1],CID,cand['symbol'],cand['side'],
             cand['ledger_m5_bar_time'],k,proof)
            ledger.queue_native_adaptive_pending(c,k,account['equity_usd'])
        # UNKNOWN is now durable: NEVER retry, even if any subsequent I/O fails.
        native.atomic_audit_client_context(folder,k,ea['nonce'],row[7],row[4],
                                           cand['symbol'],cand['side'])
        lines=['APEX_NATIVE_ADAPTIVE_ORDER_V3',ea['nonce'],k,row[7],row[4],
          cand['symbol'],cand['side'],'AUTO','0.10','STRUCTURE_M5',
          str(int(time.time()+12)),'SEND_DEMO_ONLY']
        native.atomic_native_request(folder/native.REQUEST_NAME,lines)
        result={'schema':'abutron.6207.one_shot_demo_pilot.v1','created_at_utc':utc(),
         'status':'SUBMISSION_UNKNOWN_AWAIT_NATIVE_BROKER_RECEIPT','signal_key_prefix':k[:12],
         'symbol':cand['symbol'],'model':cand['model'],'account_suffix':'6207',
         'orders_acknowledged':0,'protected_positions_verified':0,'safe_to_retry':False}
        atomic_json(AUDIT,result)
        print('6207_ONE_SHOT_NATIVE_REQUEST_PUBLISHED','UNKNOWN_NO_RETRY',k[:12])
    finally:
        os.close(fd)

def reconcile_6207():
    if os.geteuid()!=0:raise Denied('ROOT_REQUIRED')
    fd=os.open(native.ROOT/'execution-writer.lock',os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
    try:
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with ledger.new() as c:
            rows=c.execute("""SELECT signal_key,owner,connection_id,symbol,side,state,
              broker_order,broker_deal,broker_position FROM attempts WHERE connection_id=?
              AND state IN ('RESERVED','SUBMISSION_UNKNOWN','BROKER_ACK_UNRECONCILED',
              'OPEN_PROTECTED','UNPROTECTED')""",(CID,)).fetchall()
            result=[{'signal_key_prefix':x[0][:12],'outcome':native.reconcile_one(c,x)} for x in rows]
        print('6207_RECONCILE_ONLY',json.dumps(result),'NO_NEW_ORDERS')
    finally:os.close(fd)

def main():
    ap=argparse.ArgumentParser()
    mode=ap.add_mutually_exclusive_group(required=True)
    for command in ('publish','inspect','dispatch','reconcile'):mode.add_argument('--'+command,action='store_true')
    args=ap.parse_args()
    if args.publish:publish()
    elif args.inspect:
        try:
            authorize_6207(time.time())
            fresh_runtime_checks(time.time())
            cand=choose_published(time.time())
            print('6207_PILOT_READY_IF_RUN_IMMEDIATELY',cand['symbol'],cand['model'])
        except Exception as exc:print('6207_PILOT_BLOCKED',type(exc).__name__,str(exc)[:150])
    elif args.dispatch:
        try:one_shot_dispatch()
        except Denied as exc:
            if str(exc) in ('NO_PRECOMMITTED_FRESH_RESEARCH_SIGNAL','PUBLISHED_INTENT_STALE'):
                print('6207_WAIT_FOR_PRECOMMITTED_RESEARCH_SIGNAL_NO_ORDER',str(exc),flush=True)
            else:
                raise
    elif args.reconcile:reconcile_6207()
if __name__=='__main__':main()
