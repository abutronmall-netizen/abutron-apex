#!/usr/bin/python3
"""Fail-closed, read-only recovery of PRE-RECONNECT verified MT5 positions.

Never creates/rewrites EA position evidence or MT5 broker ACK receipts.
Authorizes one root-allowlisted account's historical position only when:
- immutable, previously OPEN_PROTECTED broker order/deal/position identities match;
- the current authenticated session's fresh native MQL5 position feed matches
  every broker-fed position (ticket/symbol/side/volume/entry/SL/TP);
- the broker deal originated BEFORE the current terminal instance was created;
- the current V3 EA still reports broker-native execution capability.
New trades MUST continue producing the ordinary nonce-bound evidence files.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import json
import math
import os
import sqlite3
import stat
import time
from pathlib import Path

ALLOWLIST=Path('/var/lib/apex-client-feed/legacy_9244_reconnect_continuity.json')
MAX_NATIVE_PROOF_AGE_SECONDS=12.0

def close(a,b,tol=1e-5):
    return math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a)-float(b))<=tol

def verify_prior_native_position(cid,account,ea,login,server,key,sym,side,ticket,volume,sl,tp,ledger_path,*,manifest_path=ALLOWLIST):
    """True only for a verified, pre-reconnect immutable broker position.

    This is not a fabricated 19-line EA proof. It is a verified continuity
    check using CURRENT MT5-native broker data and historically proven ledger.
    """
    if cid in PREBOOT_USD50_ALLOWLIST:
        return verify_preboot_usd50_position(
            cid, account, ea, login, server, key, sym, side, ticket,
            volume, sl, tp, ledger_path)
    try:
        if not (isinstance(cid,str) and len(cid)==32 and
                isinstance(login,str) and login.isdecimal() and
                server=='Deriv-Demo' and
                isinstance(key,str) and len(key)==64 and
                sym in account.get('occupied_symbols', [p.get('symbol') for p in account.get('positions',[])]) and
                side in ('BUY','SELL') and isinstance(ticket,int) and ticket>0 and
                ea.get('protocol_version')==3 and
                ea.get('exposure_verified') is True and
                ea.get('pending_orders')==0):
            return False
        manifest_path=Path(manifest_path)
        st=manifest_path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or (st.st_mode & 0o077)!=0 or st.st_size>12000:
            return False
        bundle=json.loads(manifest_path.read_text())
        if (bundle.get('schema')!='abutron.apex.legacy.position.reconnect_continuity.v1' or
            bundle.get('connection_id')!=cid or bundle.get('broker')!='Deriv' or
            bundle.get('environment')!='DEMO' or
            bundle.get('server')!=server or bundle.get('mt5_login')!=login or
            bundle.get('historical_policy')!={'gross_sl_usd':10,'gross_tp_usd':20}):
            return False
        records=bundle.get('positions')
        if not isinstance(records,list) or len(records)!=2 or len({r.get('signal_key') for r in records})!=2:
            return False
        record=next((r for r in records if r.get('signal_key')==key),None)
        if not record or (record.get('symbol'),record.get('side'),record.get('state'),record.get('broker_position'))!=(sym,side,'OPEN_PROTECTED',ticket):
            return False
        if not (close(record['volume'],volume) and close(record['stop_loss'],sl) and close(record['take_profit'],tp)):
            return False
        # Original native proof had already transitioned this ledger row into
        # OPEN_PROTECTED. Require unmodified broker identities and prices.
        with sqlite3.connect('file:'+str(ledger_path)+'?mode=ro',uri=True,timeout=3) as c:
            c.execute('PRAGMA query_only=ON')
            rows=c.execute("""SELECT symbol,side,state,created_at_utc,broker_order,
              broker_deal,broker_position,entry_price,stop_loss,take_profit,volume
              FROM attempts WHERE connection_id=? AND signal_key=?""",(cid,key)).fetchall()
        if len(rows)!=1:
            return False
        names=('symbol','side','state','created_at_utc','broker_order','broker_deal',
               'broker_position','entry_price','stop_loss','take_profit','volume')
        ledger=dict(zip(names,rows[0]))
        for name in names:
            if name in ('entry_price','stop_loss','take_profit','volume'):
                if not close(record[name],ledger[name]):
                    return False
            elif record[name]!=ledger[name]:
                return False
        if not (isinstance(ledger['broker_order'],int) and ledger['broker_order']>0 and
                isinstance(ledger['broker_deal'],int) and ledger['broker_deal']>0 and
                ledger['broker_position']==ticket):
            return False

        files=Path(ea['files'])
        nonce=ea.get('nonce')
        if not isinstance(nonce,str) or len(nonce)!=32:
            return False
        # The terminal binary's current inode ctime is when this isolated
        # worker copied the terminal, not the template binary's old mtime.
        exe=files.parent.parent/'terminal64.exe'
        if not exe.is_file() or exe.is_symlink():
            return False
        session_began=exe.stat().st_ctime
        opened=dt.datetime.fromisoformat(ledger['created_at_utc'].replace('Z','+00:00')).timestamp()
        if not opened<session_began-30:
            return False

        native=files/('ABUTRON_NATIVE_ACCOUNT_V2_'+nonce+'.txt')
        fst=native.lstat()
        if not stat.S_ISREG(fst.st_mode) or fst.st_size>14000:
            return False
        age=time.time()-fst.st_mtime
        if not 0<=age<=MAX_NATIVE_PROOF_AGE_SECONDS:
            return False
        lines=native.read_text(encoding='utf-8-sig').splitlines()
        if (len(lines)<7 or lines[0]!='ABUTRON_NATIVE_ACCOUNT_V2' or
            lines[1]!=nonce or lines[2]!=login or lines[5]!='USD'):
            return False
        count=int(lines[6])
        positions=account.get('positions')
        if (not isinstance(positions,list) or count!=len(lines)-7 or
            count!=len(positions) or count!=account.get('open_positions') or
            ea.get('positions')!=count or not 0<=count<=13):
            return False
        broker_by_id={}
        for entry in positions:
            if not isinstance(entry,dict) or entry.get('protected') is not True:
                return False
            pid=int(entry['ticket'])
            if pid in broker_by_id:
                return False
            broker_by_id[pid]=entry
        actual=set()
        for line in lines[7:]:
            parts=line.split('\t')
            if len(parts)!=8:
                return False
            posid=int(parts[0]);position=broker_by_id.get(posid)
            if posid in actual or position is None:
                return False
            direction='BUY' if parts[2]=='0' else 'SELL' if parts[2]=='1' else None
            if (direction is None or
                parts[1]!=position.get('symbol') or direction!=position.get('side') or
                not close(parts[3],position['volume']) or
                not close(parts[4],position['open_price']) or
                not close(parts[5],position['sl']) or
                not close(parts[6],position['tp'])):
                return False
            actual.add(posid)
        if actual!=set(broker_by_id):
            return False
        here=broker_by_id.get(ticket)
        if (not here or here.get('symbol')!=sym or here.get('side')!=side or
            not close(here['volume'],volume) or
            not close(here['open_price'],ledger['entry_price']) or
            not close(here['sl'],sl) or not close(here['tp'],tp)):
            return False
        return True
    except (KeyError,ValueError,TypeError,IndexError,OSError,sqlite3.Error,OverflowError):
        return False


# Exact, root-owned recovery scope for the two USD50/USD100 accounts whose
# native evidence was backed up BEFORE the 2026-11-05 OS reboot.
# No old receipts are copied into an MT5 terminal; this attests historical
# position continuity against independently fresh MT5-native broker positions.
PREBOOT_USD50_ALLOWLIST=frozenset((
    '1ead1f08b44dc5ae284eadc9554b1381',
    '9568525eee306da891258ad98c654919',
))
PREBOOT_USD50_DIR=Path(
    '/var/backups/abutron-postreboot-recovery-20261105/continuity-archive-usd50')


def verify_preboot_usd50_position(
    cid, account, ea, login, server, key, sym, side,
    ticket, volume, sl, tp, ledger_path, *,
    evidence_root=PREBOOT_USD50_DIR, now=None,
):
    """Fail-closed pre-OS-reboot $50/$100 evidence-to-current-broker continuity.

    Original native 19-line position evidence is SHA256-bound to a
    verified encrypted OFFSITE snapshot. A fresh nonce-bound MT5 account
    export and exact durable ledger match are REQUIRED on every call.
    This function does not fabricate a current EA receipt or authorize orders.
    """
    try:
        current=time.time() if now is None else float(now)
        if (cid not in PREBOOT_USD50_ALLOWLIST or server!='Deriv-Demo'
            or not isinstance(login,str) or not login.isdecimal()
            or side not in ('BUY','SELL') or sym not in (
                'Volatility 50 Index.0','Volatility 100 Index.0')
            or not isinstance(key,str) or len(key)!=64
            or type(ticket) is not int or ticket<=0
            or not ea or ea.get('protocol_version')!=3
            or ea.get('exposure_verified') is not True
            or ea.get('pending_orders')!=0):
            return False
        root=Path(evidence_root)
        if (root.is_symlink() or not root.is_dir()
            or root.stat().st_uid!=0 or root.stat().st_mode & 0o077):
            return False
        manifest=root/'manifest.json'
        mst=manifest.lstat()
        if (not stat.S_ISREG(mst.st_mode) or mst.st_uid!=0
            or mst.st_mode & 0o077 or mst.st_size>22000):
            return False
        doc=json.loads(manifest.read_text())
        if (doc.get('schema') !=
                'abutron.apex.deriv.immutable_preboot_native_position_evidence.v1'
            or doc.get('archive_snapshot')!='df66d1b2'
            or doc.get('environment')!='Deriv DEMO'
            or doc.get('risk_policy')!={'gross_sl_usd':50,'gross_tp_usd':100}
            or set(doc.get('accounts',{}))!=PREBOOT_USD50_ALLOWLIST):
            return False
        owner=doc['accounts'][cid]
        records=owner.get('positions')
        if (owner.get('server')!=server or owner.get('login')!=login
            or not isinstance(records,list) or len(records)!=2
            or owner.get('expected_position_count')!=2
            or len({r.get('signal_key') for r in records})!=2):
            return False
        files=Path(ea['files'])
        nonce=ea.get('nonce')
        if not isinstance(nonce,str) or len(nonce)!=32:
            return False
        exe=files.parent.parent/'terminal64.exe'
        if not exe.is_file() or exe.is_symlink():
            return False
        session=exe.stat().st_ctime
        archive_time=dt.datetime.fromisoformat(
            doc['archive_completed_utc'].replace('Z','+00:00')).timestamp()
        if not archive_time<session-60:
            return False

        # Validate the independently fresh, authenticated MQL5 broker position
        # export in this NEW terminal session before trusting any old evidence.
        source=files/('ABUTRON_NATIVE_ACCOUNT_V2_'+nonce+'.txt')
        srcst=source.lstat()
        if (not stat.S_ISREG(srcst.st_mode) or srcst.st_size>14000
            or not 0<=current-srcst.st_mtime<=12):
            return False
        native=source.read_text(encoding='utf-8-sig').splitlines()
        if (len(native)<7 or native[0]!='ABUTRON_NATIVE_ACCOUNT_V2'
            or native[1]!=nonce or native[2]!=login or native[5]!='USD'):
            return False
        count=int(native[6])
        positions=account.get('positions')
        if (not isinstance(positions,list)
            or count!=len(native)-7 or count!=len(positions)
            or account.get('open_positions')!=count
            or ea.get('positions')!=count or not 0<count<=13):
            return False
        by_ticket={}
        for p in positions:
            if not isinstance(p,dict) or p.get('protected') is not True:
                return False
            pid=int(p['ticket'])
            if pid in by_ticket:return False
            by_ticket[pid]=p
        native_tickets=set()
        for line in native[7:]:
            parts=line.split('	')
            if len(parts)!=8:return False
            pid=int(parts[0])
            p=by_ticket.get(pid)
            direction={'0':'BUY','1':'SELL'}.get(parts[2])
            if (p is None or pid in native_tickets or direction is None
                or parts[1]!=p.get('symbol') or direction!=p.get('side')
                or not close(parts[3],p['volume']) or
                not close(parts[4],p['open_price']) or
                not close(parts[5],p['sl']) or not close(parts[6],p['tp'])):
                return False
            native_tickets.add(pid)
        if native_tickets!=set(by_ticket):
            return False

        # Historical archived V1 positions may coexist with NEW positions.
        # Require strict fresh-session native evidence for every additional
        # position; never expand the archived historical allowlist itself.
        historical={r.get('broker_position'):r for r in records}
        for pid,p in by_ticket.items():
            if pid in historical:
                entry=historical[pid]
                if (p.get('symbol')!=entry.get('symbol') or
                    p.get('side')!=entry.get('side') or
                    not close(p['volume'],entry['volume']) or
                    not close(p['open_price'],entry['entry_price']) or
                    not close(p['sl'],entry['stop_loss']) or
                    not close(p['tp'],entry['take_profit'])):
                    return False
                continue
            # A newly opened position requires a current nonce-bound EA
            # position evidence file, plus immutable OPEN_PROTECTED ledger.
            with sqlite3.connect('file:'+str(ledger_path)+'?mode=ro',uri=True,timeout=3) as c:
                c.execute('PRAGMA query_only=ON')
                extra=c.execute('''SELECT signal_key,symbol,side,broker_position,
                                  volume,entry_price,stop_loss,take_profit,state
                                  FROM attempts WHERE connection_id=?
                                  AND broker_position=? AND state='OPEN_PROTECTED' ''',
                                (cid,pid)).fetchall()
            if len(extra)!=1:
                return False
            k,sym_extra,side_extra,ticket_extra,qty,price,stop,take,state=extra[0]
            if (not isinstance(k,str) or len(k)!=64 or
                sym_extra!=p.get('symbol') or side_extra!=p.get('side') or
                ticket_extra!=pid or not close(qty,p['volume']) or
                not close(price,p['open_price']) or
                not close(stop,p['sl']) or not close(take,p['tp'])):
                return False
            proof=files/'ABUTRON'/'evidence'/(k+'.txt')
            pst=proof.lstat()
            if (not stat.S_ISREG(pst.st_mode) or proof.is_symlink()
                or pst.st_size>5000 or not 0<=current-pst.st_mtime<=135):
                return False
            lines=proof.read_text(encoding='utf-8-sig').splitlines()
            if (len(lines)!=19 or lines[:7]!=
                ['APEX_BROKER_POSITION_V2',k,nonce,login,server,sym_extra,side_extra]
                or lines[16]!='OPEN_PROTECTED' or
                int(lines[9])!=pid or
                not -5<=current-int(lines[17])<=135 or
                not all(close(x,y) for x,y in
                  ((lines[10],qty),(lines[11],price),(lines[12],stop),(lines[13],take)))):
                return False
            cash_sl=float(lines[14]);cash_tp=float(lines[15])
            if not ((abs(cash_sl-50.0)<=2.0 and abs(cash_tp-100.0)<=2.0)
                or (abs(cash_sl-10.0)<=2.0 and abs(cash_tp-20.0)<=2.0)):
                return False
        record=next((r for r in records if r.get('signal_key')==key),None)
        if (record is None or record.get('broker_position')!=ticket or
            record.get('symbol')!=sym or record.get('side')!=side or
            not close(record['volume'],volume) or
            not close(record['stop_loss'],sl) or not close(record['take_profit'],tp)):
            return False
        active=by_ticket.get(ticket)
        if active is None:
            return False

        # Source evidence is the unchanged, captured-before-reboot 19-line
        # EA proof from Restic; hash, nonce, account, risk and broker identities
        # are checked against the current immutable OPEN_PROTECTED ledger.
        archive=root/cid/(key+'.txt')
        ast=archive.lstat()
        if (not stat.S_ISREG(ast.st_mode) or ast.st_uid!=0
            or ast.st_mode & 0o077 or ast.st_size>5000):
            return False
        raw=archive.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=record.get('archive_proof_sha256'):
            return False
        lines=raw.decode('utf-8-sig').splitlines()
        if (len(lines)!=19 or lines[0:2]!=['APEX_BROKER_POSITION_V2',key]
            or lines[2]==nonce or lines[3:7]!=[login,server,sym,side]
            or lines[16]!='OPEN_PROTECTED'
            or abs(float(lines[14])-50)>2 or abs(float(lines[15])-100)>2
            or int(lines[17])>=session-15):
            return False
        with sqlite3.connect('file:'+str(ledger_path)+'?mode=ro',uri=True,timeout=3) as db:
            db.execute('PRAGMA query_only=ON')
            proof=db.execute("""SELECT owner,broker,environment,symbol,side,state,
                broker_order,broker_deal,broker_position,volume,
                entry_price,stop_loss,take_profit,created_at_utc
                FROM attempts WHERE connection_id=? AND signal_key=?""",
                (cid,key)).fetchall()
        if len(proof)!=1:return False
        (ledger_owner,broker,mode,lsym,lside,state,order,deal,pos,
         vol,price,lstop,ltake,created)=proof[0]
        if (ledger_owner!=owner.get('account_id')
            or (broker,mode,lsym,lside,state)!=
                ('Deriv','DEMO',sym,side,'OPEN_PROTECTED')
            or (order,deal,pos)!=(record['broker_order'],
                                  record['broker_deal'],ticket)
            or [int(x) for x in lines[7:10]]!=[order,deal,pos]
            or not (order>0 and deal>0 and pos>0)
            or not all(close(a,b) for a,b in
                ((lines[10],vol),(lines[11],price),(lines[12],lstop),
                 (lines[13],ltake),(vol,volume),(lstop,sl),(ltake,tp)))
            or not close(price,active['open_price'])
            or dt.datetime.fromisoformat(
                created.replace('Z','+00:00')).timestamp()>=session-30):
            return False
        return True
    except (KeyError,ValueError,TypeError,IndexError,OSError,
            sqlite3.Error,OverflowError,AttributeError):
        return False
