"""Redis-backed staged MT5 customer second factor. No broker or order access.
Only caller-proven portal owners may invoke; private delivery required.
"""
from __future__ import annotations
import hashlib,hmac,ipaddress,time
from app.customer_stepup_core import issue,verify,ProofRejected,owner_uuid

class StepupUnavailable(Exception):pass

THROTTLE_LUA="""
local a=tonumber(redis.call('GET',KEYS[1]) or '0')
local b=tonumber(redis.call('GET',KEYS[2]) or '0')
if a>=3 or b>=12 then return 0 end
redis.call('INCR',KEYS[1]); redis.call('EXPIRE',KEYS[1],900)
redis.call('INCR',KEYS[2]); redis.call('EXPIRE',KEYS[2],900)
return 1
"""

def digest(secret,label,value):
    return hmac.new(secret,("abutron:mt5-stepup:"+label+":"+value).encode(),
                    hashlib.sha256).hexdigest()

def client_address(value):
    try:return str(ipaddress.ip_address(value))
    except (ValueError,TypeError):raise StepupUnavailable("VALIDATED_NETWORK_ID_REQUIRED") from None

async def begin(*,redis,secret:bytes,owner:str,auth_version:str,
                remote_ip:str,fresh_auth:bool,send_private_code,now=None):
    if fresh_auth is not True:raise StepupUnavailable("FRESH_PORTAL_AUTH_REQUIRED")
    owner_uuid(owner)
    if not isinstance(auth_version,str) or len(auth_version)<32:
        raise StepupUnavailable("VALID_SESSION_VERSION_REQUIRED")
    ip=client_address(remote_ip)
    t=int(time.time()) if now is None else int(now)
    owner_key="abutron:mt5:stepup:lim:owner:"+digest(secret,"owner",owner)
    network_key="abutron:mt5:stepup:lim:ip:"+digest(secret,"ip",ip)
    try:
        quota=await redis.eval(THROTTLE_LUA,2,owner_key,network_key)
        if int(quota)!=1:raise StepupUnavailable("MT5_MFA_RATE_LIMITED")
    except StepupUnavailable:raise
    except Exception:raise StepupUnavailable("MT5_MFA_RATE_LIMIT_UNAVAILABLE") from None
    proof=issue(secret,owner)
    key="abutron:mt5:stepup:challenge:"+digest(secret,"challenge",proof.challenge)
    expected=auth_version+"|"+owner+"|"+str(t)+"|"+proof.expected_digest
    try:
        ok=await redis.set(key,expected,ex=300,nx=True)
        if not ok:raise StepupUnavailable("CHALLENGE_ALREADY_EXISTS")
        await send_private_code(proof.private_delivery_code)
    except Exception:
        try:await redis.delete(key)
        except Exception:pass
        raise StepupUnavailable("PRIVATE_DELIVERY_UNAVAILABLE") from None
    return {"challenge":proof.challenge,"expires_seconds":300,
            "broker_enrollment_enabled":False,"order_execution_enabled":False}

async def complete(*,redis,secret:bytes,owner:str,auth_version:str,
                   challenge:str,code:str,now=None):
    owner_uuid(owner)
    if not isinstance(challenge,str) or len(challenge)!=43:
        raise StepupUnavailable("INVALID_OR_EXPIRED_MFA")
    if not isinstance(code,str) or len(code)!=6 or not code.isascii() or not code.isdecimal():
        raise StepupUnavailable("INVALID_OR_EXPIRED_MFA")
    key="abutron:mt5:stepup:challenge:"+digest(secret,"challenge",challenge)
    try:
        entry=await redis.getdel(key)
    except Exception:
        raise StepupUnavailable("MFA_BACKEND_UNAVAILABLE") from None
    if not isinstance(entry,str):
        raise StepupUnavailable("INVALID_OR_EXPIRED_MFA")
    try:
        version,subject,created,expected=entry.split("|",3)
        clock=int(time.time()) if now is None else int(now)
        if not hmac.compare_digest(version,auth_version) or subject!=owner or not (0<=clock-int(created)<=300):
            raise StepupUnavailable("INVALID_OR_EXPIRED_MFA")
        result=verify(secret,owner,challenge,code,expected)
    except (ValueError,ProofRejected,StepupUnavailable):
        raise StepupUnavailable("INVALID_OR_EXPIRED_MFA") from None
    return {"mfa_verified":result["stepup_valid"],
            "broker_enrollment_enabled":False,
            "broker_password_collection_enabled":False,
            "order_execution_enabled":False}
