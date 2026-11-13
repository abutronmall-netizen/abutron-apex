"""Root-isolated single-recipient APEX admin email MFA sender using existing Resend config.

Runs only from a systemd unit with protected EnvironmentFile.
Never logs API keys or email verification codes.
"""
import datetime as dt
import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
sys.path.insert(0,"/opt/apex-signup")
sys.path.insert(0,"/opt/apex-client-portal")
import apex_admin

DBFILE=Path("/var/lib/apex-signup/accounts.sqlite3")
SECRET=Path("/var/lib/apex-signup/admin_mfa_secret")
def connect():
 c=sqlite3.connect(DBFILE,timeout=15,isolation_level=None)
 c.execute("PRAGMA foreign_keys=ON")
 c.execute("PRAGMA busy_timeout=15000")
 return c
def main():
 key=os.environ.get("ABUTRON_RESEND_API_KEY","").strip().strip('"').strip("'")
 sender=os.environ.get("ABUTRON_VERIFICATION_FROM_EMAIL","").strip().strip('"').strip("'")
 if not key or not sender or "@" not in sender:
  raise RuntimeError("ADMIN_MAILER_CONFIGURATION_UNAVAILABLE")
 apex_admin.configure(connect,SECRET)
 with connect() as c:
  c.execute("BEGIN IMMEDIATE")
  moment=int(time.time())
  job=c.execute("""SELECT ch.challenge_id,ch.account_id,a.email,ch.expires_at,j.attempts
                 FROM apex_admin_challenges ch JOIN apex_admin_mail_jobs j ON j.challenge_id=ch.challenge_id
                 JOIN accounts a ON a.id=ch.account_id
                 WHERE j.status='queued' AND j.updated_at<=?
                 ORDER BY ch.created_at LIMIT 1""",(moment,)).fetchone()
  if not job:
   c.execute("COMMIT")
   print("ADMIN_MAIL_NO_PENDING_CHALLENGE")
   return
  cid,aid,email,expiry,attempts=job
  if email!=apex_admin.ADMIN_EMAIL or moment>=expiry:
   c.execute("UPDATE apex_admin_mail_jobs SET status='failed',updated_at=? WHERE challenge_id=?",(moment,cid))
   c.execute("COMMIT")
   print("ADMIN_MAIL_EXPIRED_OR_RECIPIENT_BLOCKED")
   return
  c.execute("""UPDATE apex_admin_mail_jobs SET status='sending',attempts=attempts+1,
               updated_at=? WHERE challenge_id=?""",(moment,cid))
  c.execute("COMMIT")
 code=apex_admin.otp_for(aid,cid)
 body={
  "from":sender,"to":[email],
  "subject":"ABUTRON Superadmin — email verification code",
  "text":("Your ABUTRON Superadmin verification code is: "+code+
         "\n\nThis code expires in 10 minutes. It does not enable trading or payments."+
         "\nIf you did not request it, ignore this email.\n")
 }
 req=urllib.request.Request("https://api.resend.com/emails",
      data=json.dumps(body).encode(),method="POST",
      headers={"Authorization":"Bearer "+key,"Content-Type":"application/json",
               "User-Agent":"APEX-Transactional/1.0"})
 successful=False
 try:
  with urllib.request.urlopen(req,timeout=13) as res:
   successful=res.status in (200,201,202)
 except urllib.error.HTTPError as exc:
  # Log HTTP status only; no sensitive response details.
  print("ADMIN_MFA_PROVIDER_HTTP_STATUS",exc.code)
  successful=False
 except (urllib.error.URLError,TimeoutError,OSError) as exc:
  print("ADMIN_MFA_PROVIDER_ERROR_TYPE",type(exc).__name__)
  successful=False
 with connect() as c:
  c.execute("BEGIN IMMEDIATE")
  moment=int(time.time())
  if successful:
   c.execute("UPDATE apex_admin_mail_jobs SET status='sent',updated_at=? WHERE challenge_id=?",(moment,cid))
   c.execute("UPDATE apex_admin_challenges SET delivered_at=? WHERE challenge_id=?",(moment,cid))
   apex_admin.log(c,"ADMIN_MFA_EMAIL_DELIVERY_ACCEPTED",aid)
   print("ADMIN_MFA_EMAIL_ACCEPTED_BY_PROVIDER")
  else:
   state="failed" if attempts+1>=3 or moment>=expiry else "queued"
   next_at=moment+30 if state=="queued" else moment
   c.execute("UPDATE apex_admin_mail_jobs SET status=?,updated_at=? WHERE challenge_id=?",(state,next_at,cid))
   apex_admin.log(c,"ADMIN_MFA_EMAIL_SEND_FAILED",aid,state)
   print("ADMIN_MFA_EMAIL_DELIVERY_FAILED",state)
  c.execute("COMMIT")
if __name__=="__main__":main()
