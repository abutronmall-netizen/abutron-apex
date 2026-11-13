#!/usr/bin/python3
"""ABUTRON APEX 1.1 Deriv DEMO 6207 CRM activation ack (not broker order ACK).
Replaces the old Qlib/V3 6207 acknowledgment on the EXISTING timer.
No orders, no live switch, no new veto/reviewer/certification services.
"""
from __future__ import annotations
import argparse,json,os,sqlite3,time
from datetime import datetime,timezone
from pathlib import Path

CID='d6fc2524ec373b8d1bc278a8be3ec635'
DB='/var/lib/apex-signup/accounts.sqlite3'
PROOF=Path('/var/lib/abutron-v4-broker-crm-supervisor-6207/evidence.json')
HASH='83f9ea4c23f81064a1fcdfe9c902f1a9824799d99d799e52d02e5ea3a1dec275'
CHART=Path('/var/lib/abutron-v4-broker-crm-supervisor-6207/v4-ro-attachment-evidence.json')
CHECKS=(
 'root_inspector','apex_crm_owner_mfa_account_binding','apex_enterprise_license',
 'apex_v7_same_owner','v7_remains_readonly','crm_monotonic_revision_ledger',
 'client_requested_on','deriv_worker_fresh_identity',
 'deriv_independent_readonly_broker_session','deriv_native_account_snapshot',
 'live_orders_disabled','v4_sha256_binary_installed',
 
 
 'customer_cashflow_adjusted_portfolio_risk',
 'root_native_writer_lock_file','exclusive_writer_and_unknown_orders_reconciled',
 'unapproved_dispatch_inactive'
)

def inspect():
    p=PROOF
    if p.is_symlink() or not p.is_file():return False,'NATIVE_6207_SUPERVISOR_ABSENT'
    st=p.stat()
    if st.st_uid!=0 or st.st_mode&0o022 or not -3<=time.time()-st.st_mtime<=95:
        return False,'NATIVE_6207_SUPERVISOR_STALE'
    try:d=json.loads(p.read_text())
    except (OSError,ValueError):return False,'NATIVE_6207_SUPERVISOR_INVALID'
    if (d.get('schema')!='abutron.v4.broker_crm.readonly.admission.v1'
        or d.get('account_suffix')!='6207' or d.get('broker')!='Deriv'
        or d.get('environment')!='DEMO' or d.get('orders_submitted')!=0
        or d.get('client_switches_modified') is not False
        or d.get('read_only_evidence_only') is not True):
        return False,'NATIVE_6207_SUPERVISOR_ACCOUNT_MISMATCH'
    cs=d.get('checks',{})
    missing=[k for k in CHECKS if cs.get(k) is not True]
    if missing:return False,'NATIVE_6207_NOT_READY:'+','.join(missing[:3])
    # Use the existing independent V4 chart proof, not an HTTP/CRM lease
    # that is impossible to renew until the CRM account is effective ON.
    try:
        st=CHART.lstat()
        if (CHART.is_symlink() or st.st_uid!=0 or st.st_mode&0o022
            or not -3<=time.time()-st.st_mtime<=65):
            return False,'NATIVE_V4_CHART_PROOF_STALE'
        chart=json.loads(CHART.read_text())
        ch=chart.get('checks',{})
        if (chart.get('schema')!='abutron.v4.native.chart_attachment.v2'
            or chart.get('state')!='V4_NATIVE_CHART_ATTACHED'
            or chart.get('metrics',{}).get('release_sha256')!=HASH
            or chart.get('metrics',{}).get('automatic_order_input_enabled_at_last_init') is not True
            or not all(ch.get(k) is True for k in (
                'exact_v4_release_binary_installed',
                'fresh_deriv_6207_demo_worker','independent_native_mt5_chart_load',
                'native_worker_unit_active','v4_expert_native_oninit_proven'))):
            return False,'NATIVE_V4_CHART_PROOF_INVALID'
    except (OSError,ValueError,TypeError):
        return False,'NATIVE_V4_CHART_PROOF_UNAVAILABLE'
    m=d.get('metrics',{})
    risk=m.get('apex11_owner_operational_risk',{})
    if (risk.get('owner_native_current_risk_proven') is not True
        or risk.get('preserved_2pct_aggregate_stop_risk') is not True
        or risk.get('preserved_3pct_daily_cash_loss_limit') is not True
        or risk.get('preserved_20pct_portfolio_open_risk_ceiling') is not True):
        return False,'APEX11_OWNER_RISK_UNVERIFIED'
    if not isinstance(m.get('crm_revision'),int) or m['crm_revision']<1:
        return False,'CRM_REVISION_UNKNOWN'
    return True,'APEX11_NATIVE_DEMO_PROVEN'

def activate():
    if os.geteuid()!=0:raise RuntimeError('ROOT_REQUIRED')
    eligible,reason=inspect()
    now=int(time.time())
    with sqlite3.connect(DB,timeout=10,isolation_level=None) as c:
        c.execute('PRAGMA busy_timeout=10000')
        c.execute('BEGIN IMMEDIATE')
        try:
            row=c.execute('''SELECT x.account_id,x.broker,x.environment,x.account_reference,
                              x.broker_server,x.status,a.status,
                              t.desired_enabled,t.effective_enabled,
                              f.revision,f.desired_enabled,f.effective_enabled,f.connection_status
                              FROM apex_mt5_connections x
                              JOIN accounts a ON a.id=x.account_id
                              JOIN apex_trade_controls t ON t.connection_id=x.id
                              JOIN abutron_v4_6207_activation_revision f ON f.connection_id=x.id
                              WHERE x.id=?''',(CID,)).fetchone()
            if not row:raise RuntimeError('CRM_6207_ACCOUNT_MISSING')
            (owner,broker,env,login,server,conn,approved,
             desired,effective,rev,fd,fe,fc)=row
            bound=(broker,env,login,server,conn,approved)==(
                   'Deriv','DEMO','32456207','Deriv-Demo','CONNECTED','approved')
            revision_consistent=(fd,fe,fc)==(desired,effective,conn)
            permit=bool(eligible and desired==1 and bound and revision_consistent)
            action='UNCHANGED'
            if desired!=1 or not bound or not revision_consistent:
                permit=False
            if permit and effective!=1:
                changed=c.execute('''UPDATE apex_trade_controls SET effective_enabled=1,
                             updated_at=?,last_error=NULL
                             WHERE connection_id=? AND desired_enabled=1 AND effective_enabled=0''',
                             (now,CID)).rowcount
                if changed!=1:raise RuntimeError('ACTIVATION_CONCURRENT_CHANGE')
                action='ACTIVATED_DEMO'
            elif not permit and effective!=0:
                changed=c.execute('''UPDATE apex_trade_controls SET effective_enabled=0,
                           updated_at=?,last_error=?
                           WHERE connection_id=? AND effective_enabled=1''',
                           (now,reason[:120],CID)).rowcount
                if changed!=1:raise RuntimeError('DEACTIVATION_CONCURRENT_CHANGE')
                action='DEACTIVATED_DEMO'
            f=c.execute('''SELECT revision,desired_enabled,effective_enabled,connection_status
                         FROM abutron_v4_6207_activation_revision WHERE connection_id=?''',
                         (CID,)).fetchone()
            if not f or f[1:]!=(desired,int(permit),conn):
                raise RuntimeError('REVISION_FENCED_CRM_STATE_MISMATCH')
            if permit:
                c.execute('''UPDATE abutron_v4_6207_activation_revision
                         SET ack_revision=?,ack_expires_utc=?,
                             updated_utc=?,last_event='APEX11_NATIVE_DEMO_READY_ACK'
                         WHERE connection_id=? AND revision=?''',
                         (f[0],now+45,datetime.now(timezone.utc).isoformat(),
                          CID,f[0]))
            else:
                c.execute('''UPDATE abutron_v4_6207_activation_revision
                         SET ack_revision=NULL,ack_expires_utc=NULL,
                             updated_utc=?,last_event='APEX11_DEMO_OFF_OR_RISK_UNVERIFIED'
                         WHERE connection_id=?''',
                         (datetime.now(timezone.utc).isoformat(),CID))
            if action!='UNCHANGED':
                c.execute('''INSERT INTO apex_trade_control_audit
                        (account_id,connection_id,requested_enabled,outcome,occurred_at)
                        VALUES(?,?,?,?,?)''',
                        (owner,CID,desired,
                         'APEX11_6207_NATIVE_DEMO_SESSION_READY_NO_ORDER' if permit
                         else 'APEX11_6207_EFFECTIVE_OFF_NO_ORDER',now))
            c.execute('COMMIT')
            return dict(state=action,effective_demo_on=permit,revision=f[0],
                        activation_revision_ack=permit,
                        broker_execution_ack=False,orders_submitted=0)
        except BaseException:
            c.execute('ROLLBACK');raise

def main():
    a=argparse.ArgumentParser()
    a.add_argument('--inspect',action='store_true')
    a.add_argument('--ack',action='store_true')
    args=a.parse_args()
    if args.ack==args.inspect:raise SystemExit('CHOOSE_INSPECT_OR_ACK')
    if args.inspect:
        ok,reason=inspect()
        print(json.dumps(dict(state='READY_FOR_NATIVE_DEMO_ACK' if ok else 'BLOCKED',
                              reason=reason,orders_submitted=0,
                              broker_execution_ack=False,live_enabled=False)))
    else:
        print(json.dumps(activate()))
if __name__=='__main__':main()
