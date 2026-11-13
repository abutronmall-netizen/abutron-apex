#!/usr/bin/env python3
"""Existing APEX Deriv/FP bridge: strict authenticated native adaptive intent.
Offline validation only; no broker execution, no service changes.

The native EA emits OptionCWriteIntent BEFORE OrderSend. The separate native
proof must be bound to the exact immutable signal, account, position and entry.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
from pathlib import Path
import re,math,stat,time

HEX64=re.compile(r'^[a-f0-9]{64}$')
HEX32=re.compile(r'^[a-f0-9]{32}$')
class ContractViolation(ValueError): pass

def require(ok:bool,why:str):
    if not ok:raise ContractViolation(why)

def decimal(s, *, positive=False)->Decimal:
    require(type(s) in (str,int,float,Decimal),'NON_NUMERIC_RISK')
    try:d=Decimal(str(s))
    except (InvalidOperation,ValueError):raise ContractViolation('NON_NUMERIC_RISK')
    require(d.is_finite() and (d>0 if positive else d>=0),'INVALID_DECIMAL_RISK')
    return d

def parse_native_intent(path:Path,key:str,nonce:str,login:str,server:str, symbol:str,side:str,now=None)->dict:
    """Validate the 14-line broker-native file written BEFORE sending."""
    now=time.time() if now is None else float(now)
    path=Path(path)
    require(HEX64.fullmatch(key) is not None,'INVALID_SIGNAL_KEY')
    require(HEX32.fullmatch(nonce) is not None,'INVALID_SESSION_NONCE')
    require(server in ('Deriv-Demo','FPMarketsSC-Demo'),'LIVE_OR_FOREIGN_SERVER_DENIED')
    require(login.isdigit() and len(login)>=4,'INVALID_BROKER_LOGIN')
    require(side in ('BUY','SELL') and isinstance(symbol,str) and 1<=len(symbol)<=64,'INVALID_SYMBOL_SIDE')
    require(path.name==key+'.txt' and path.parent.name=='optionc_v2','UNTRUSTED_INTENT_PATH')
    try:
        st=path.lstat()
        require(stat.S_ISREG(st.st_mode) and st.st_size<3000,'INVALID_NATIVE_INTENT_FILE')
        require(-5<=now-st.st_mtime<=86400*60,'INVALID_INTENT_FILE_AGE')
        r=path.read_text(encoding='utf-8-sig').splitlines()
    except OSError as exc:raise ContractViolation('NATIVE_INTENT_UNAVAILABLE') from exc
    require(len(r)==14 and r[:7]==['APEX_OPTIONC_NATIVE_RISK_INTENT_V2',
            key,nonce,login,server,symbol,side],'NATIVE_INTENT_IDENTITY_MISMATCH')
    equity,budget,lots,original_entry,stop,target=(decimal(x,positive=True) for x in r[7:13])
    stamp=int(r[13])
    require(0<=now-stamp<=86400*60,'NATIVE_INTENT_TIMESTAMP_INVALID')
    require(budget<=equity*Decimal('0.001'),'EXCEEDS_POINT_ONE_PERCENT_EQUITY')
    require(budget>0 and lots>0 and original_entry>0,'EMPTY_NATIVE_INTENT')
    require((stop<original_entry<target if side=='BUY' else target<original_entry<stop),
            'INVALID_INTENT_STOP_GEOMETRY')
    return {'broker':('Deriv' if server=='Deriv-Demo' else 'FP Markets'),
       'key':key,'nonce':nonce,'login':login,'server':server,
       'symbol':symbol,'side':side,'equity_at_entry':equity,
       'entry_budget':budget,'lots':lots,'intended_entry':original_entry,
       'stop':stop,'target':target,'timestamp':stamp}

def native_position_risk(intent:dict, *,
                         broker_position_volume,broker_entry,broker_stop,broker_target,
                         broker_cash_loss,broker_cash_reward)->dict:
    """Only actual broker-native stop P/L is acceptable, NOT a tick-value guess."""
    volume=decimal(broker_position_volume,positive=True)
    entry=decimal(broker_entry,positive=True)
    stop=decimal(broker_stop,positive=True)
    target=decimal(broker_target,positive=True)
    risk=decimal(broker_cash_loss)
    reward=decimal(broker_cash_reward,positive=True)
    require(abs(volume-intent['lots'])<=Decimal('.0000001'),'NATIVE_VOLUME_MISMATCH')
    require(abs(target-intent['target'])<=Decimal('.0000001'),'NATIVE_TARGET_MISMATCH')
    # Broker SL may ratchet toward profit, never away from the immutable entry SL.
    buy=intent['side']=='BUY'
    require((stop>=intent['stop'] and stop<target if buy else
             stop<=intent['stop'] and stop>target),'NATIVE_STOP_NOT_IMPROVED')
    require((entry<target if buy else target<entry),'BROKER_TARGET_GEOMETRY_INVALID')
    # Zero remaining loss is valid only once the broker stop has crossed entry.
    if (stop>entry if buy else stop<entry):
        require(risk==0,'POSITIVE_STOP_LOSS_RISK_MUST_BE_ZERO')
    else:
        require(risk>0,'AT_RISK_POSITION_REQUIRES_POSITIVE_NATIVE_RISK')
    require(risk<=min(intent['entry_budget']*Decimal('1.01'),intent['equity_at_entry']*Decimal('.001'))+Decimal('.005'),'BROKER_OPEN_STOP_OVER_APPROVED_BUDGET')
    require(reward>=risk*Decimal('1.5'),'BROKER_NATIVE_REWARD_RISK_TOO_LOW')
    require(risk<=intent['equity_at_entry']*Decimal('0.001')+Decimal('.005'),
            'BROKER_NATIVE_RISK_OVER_POINT_ONE_PERCENT')
    return {'schema':'abutron.apex.native.v2.protection',
            'risk_usd':risk,'target_usd':reward,'equity_at_entry':intent['equity_at_entry'],
            'budget_usd':intent['entry_budget'],'volume':volume,'entry':entry,
            'stop':stop,'target':target,'protocol':'ADAPTIVE_V2'}
