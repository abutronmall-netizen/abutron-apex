"""Customer MT5-link second-factor proof; staged only. No email or broker calls."""
import hashlib,hmac,re,secrets,uuid
from dataclasses import dataclass

PURPOSE="MT5_LINK_STEPUP_V1"
class ProofRejected(Exception):pass

def owner_uuid(value):
    try:
        ident=uuid.UUID(value)
        if ident.version!=4 or str(ident)!=value:raise ValueError()
        return value
    except (TypeError,ValueError,AttributeError):
        raise ProofRejected("OWNER_REQUIRED") from None

def code_digest(secret,owner,challenge,code):
    if not isinstance(secret,bytes) or len(secret)<32:raise ProofRejected("KEY_REQUIRED")
    return hmac.new(secret,(PURPOSE+"|"+owner+"|"+challenge+"|"+code).encode(),hashlib.sha256).hexdigest()

@dataclass(frozen=True)
class NewProof:
    challenge:str
    private_delivery_code:str
    expected_digest:str

def issue(secret,owner):
    owner_uuid(owner)
    challenge=secrets.token_urlsafe(32)
    code=f"{secrets.randbelow(1000000):06d}"
    return NewProof(challenge,code,code_digest(secret,owner,challenge,code))

def verify(secret,owner,challenge,code,stored_digest):
    owner_uuid(owner)
    if not isinstance(challenge,str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}",challenge):
        raise ProofRejected("INVALID_PROOF")
    if not isinstance(code,str) or not re.fullmatch(r"[0-9]{6}",code):
        raise ProofRejected("INVALID_PROOF")
    if not isinstance(stored_digest,str) or not re.fullmatch(r"[a-f0-9]{64}",stored_digest):
        raise ProofRejected("INVALID_PROOF")
    if not hmac.compare_digest(stored_digest,code_digest(secret,owner,challenge,code)):
        raise ProofRejected("INVALID_PROOF")
    return {"stepup_valid":True,"password_collection_authorized":False,
            "broker_account_verified":False,"order_execution_authorized":False}
