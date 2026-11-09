"""APEX customer MT5 one-time email code sender. Never logs email, code or key."""
from __future__ import annotations
import json,os,pwd,sqlite3,stat,sys,time,urllib.error,urllib.request
from pathlib import Path
sys.path.insert(0,"/opt/apex-client-portal")
import apex_mt5_mfa as mfa

DB=Path("/var/lib/apex-signup/accounts.sqlite3")
def connect():
    db=sqlite3.connect(DB,timeout=12,isolation_level=None)
    db.execute("PRAGMA busy_timeout=12000")
    db.execute("PRAGMA foreign_keys=ON")
    return db

def main():
    if os.geteuid()!=0:raise RuntimeError("ROOT_ISOLATED_MAILER_REQUIRED")
    key=os.environ.get("ABUTRON_RESEND_API_KEY","").strip().strip('"').strip("'")
    sender=os.environ.get("ABUTRON_VERIFICATION_FROM_EMAIL","").strip().strip('"').strip("'")
    if not key or len(key)<18 or not sender or "@" not in sender:
        raise RuntimeError("MAILER_CONFIGURATION_UNAVAILABLE")
    s=mfa.SECRET_PATH.lstat()
    if (s.st_uid!=pwd.getpwnam("apexsignup").pw_uid
        or stat.S_IMODE(s.st_mode)!=0o600 or not stat.S_ISREG(s.st_mode)):
        raise RuntimeError("MFA_KEY_UNSAFE")
    secret=mfa.SECRET_PATH.read_bytes()
    if len(secret)!=32:raise RuntimeError("MFA_KEY_INVALID")
    now=int(time.time())
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        db.execute("""UPDATE apex_mt5_mfa SET email_state='queued'
           WHERE email_state='sending' AND email_next_at<=?
             AND email_attempts<3 AND expires_at>?""",(now,now))
        row=db.execute("""SELECT m.id,m.account_id,m.connection_id,m.session_hash,m.expires_at,
               m.email_attempts,a.email
           FROM apex_mt5_mfa m
           JOIN accounts a ON a.id=m.account_id
           WHERE m.email_state='queued' AND m.email_next_at<=?
             AND m.expires_at>? AND m.consumed_at IS NULL
             AND a.status='approved'
           ORDER BY m.created_at LIMIT 1""",(now,now)).fetchone()
        if not row:
            db.execute("COMMIT")
            print("APEX_MT5_MFA_MAIL_IDLE")
            return
        cid,owner,conn,session,expiry,attempts,email=row
        db.execute("""UPDATE apex_mt5_mfa SET email_state='sending',email_attempts=email_attempts+1,
             email_next_at=? WHERE id=?""",(now+90,cid))
        db.execute("COMMIT")
    otp=mfa.code_for(secret,cid,owner,conn,session,expiry)
    body={
      "from":sender,"to":[email],
      "subject":"ABUTRON MT5 account authorization code",
      "text":("Your ABUTRON MT5 account authorization code is: "+otp+
              "\n\nThis code expires in 10 minutes and authorizes one broker-login attempt only."+
              "\nIt does not authorize trading or fund an account."+
              "\nIf you did not request this, ignore the email. Do not share your MT5 password.\n")
    }
    request=urllib.request.Request("https://api.resend.com/emails",
         data=json.dumps(body).encode(),method="POST",
         headers={"Authorization":"Bearer "+key,
                  "Content-Type":"application/json",
                  "User-Agent":"APEX-MT5-OTP/1.0"})
    accepted=False
    try:
        with urllib.request.urlopen(request,timeout=15) as response:
            accepted=response.status in (200,201,202)
    except urllib.error.HTTPError as e:
        print("APEX_MT5_MFA_PROVIDER_HTTP",e.code)
    except (urllib.error.URLError,TimeoutError,OSError) as e:
        print("APEX_MT5_MFA_PROVIDER_NETWORK",type(e).__name__)
    finally:
        otp=""
        body.clear()
        key=""
    with connect() as db:
        db.execute("BEGIN IMMEDIATE")
        when=int(time.time())
        if accepted and expiry>when:
            db.execute("""UPDATE apex_mt5_mfa SET email_state='sent',
              email_sent_at=?,email_next_at=? WHERE id=? AND email_state='sending'""",
              (when,when,cid))
            print("APEX_MT5_MFA_DELIVERY_ACCEPTED")
        else:
            state="failed" if attempts+1>=3 or expiry<=when else "queued"
            next_at=when+40 if state=="queued" else when
            db.execute("""UPDATE apex_mt5_mfa SET email_state=?,email_next_at=?
                  WHERE id=? AND email_state='sending'""",
                  (state,next_at,cid))
            print("APEX_MT5_MFA_DELIVERY_NOT_CONFIRMED")
        db.execute("COMMIT")
if __name__=="__main__":
    main()
