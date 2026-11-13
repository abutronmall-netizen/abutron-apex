"""Public APEX email verification & password reset API. Same-origin POST only."""
import json, re, sqlite3, time
import account_flow

ROUTES={
 "/account/api/account/verify",
 "/account/api/account/resend",
 "/account/api/account/password/request",
 "/account/api/account/password/confirm",
}
def handle(h, registration):
    if h.headers.get("Origin") not in registration.ALLOWED_ORIGINS:
        return h.send_json(403,{"error":"Secure ABUTRON website required."})
    if h.headers.get("Sec-Fetch-Site","same-origin") not in ("same-origin","none"):
        return h.send_json(403,{"error":"Cross-site requests are blocked."})
    if h.headers.get("Content-Type","").split(";")[0].strip().lower()!="application/json":
        return h.send_json(415,{"error":"JSON required."})
    try:
        n=int(h.headers.get("Content-Length","0"))
        if n<1 or n>4096:
            raise ValueError("size")
        x=json.loads(h.rfile.read(n))
        if not isinstance(x,dict):
            raise ValueError("body")
    except (ValueError,UnicodeError):
        return h.send_json(400,{"error":"Invalid request."})
    path=h.path
    if path=="/account/api/account/verify":
        if set(x)!={"token"}:
            return h.send_json(422,{"error":"Verification link required."})
        with registration.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            valid=account_flow.consume(c,x.get("token"),"verify")
            c.execute("COMMIT")
        return h.send_json(200 if valid else 400,
            {"status":"email_verified","next":"/account/client/"} if valid
            else {"error":"Verification link expired or already used. Request a new link."})
    if path=="/account/api/account/password/confirm":
        password=x.get("password")
        if not isinstance(password,str) or not 12<=len(password)<=128 or len(x)!=2:
            return h.send_json(422,{"error":"Use a password of 12–128 characters."})
        if not isinstance(x.get("token"),str):
            return h.send_json(422,{"error":"Reset link required."})
        # Apply an IP rate limit before the memory-hard password hashing work.
        ip=h.headers.get("X-APEX-Client-IP","")
        if not re.fullmatch(r"[0-9a-fA-F:.]{3,75}",ip):
            return h.send_json(403,{"error":"Secure client route required."})
        now=int(time.time()); digest=registration.ip_digest(ip)
        with registration.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            c.execute("DELETE FROM email_rate_events WHERE created_at<?",(now-86400,))
            attempts=c.execute("SELECT COUNT(*) FROM email_rate_events WHERE ip_hmac=? AND created_at>?",(digest,now-3600)).fetchone()[0]
            if attempts>=10:
                c.execute("ROLLBACK")
                return h.send_json(429,{"error":"Too many account requests. Try again later."})
            c.execute("INSERT INTO email_rate_events(ip_hmac,created_at) VALUES(?,?)",(digest,now))
            c.execute("COMMIT")
        # Limit expensive password hashing, without holding an immediate SQLite lock.
        if not registration.PASSWORD_SEMAPHORE.acquire(blocking=False):
            return h.send_json(429,{"error":"Try again shortly."})
        try:
            pw=registration.password_hash(password)
            with registration.connect() as c:
                c.execute("BEGIN IMMEDIATE")
                ok=account_flow.consume(c,x["token"],"reset",
                    password_hasher=lambda _:pw,new_password=password)
                c.execute("COMMIT")
        finally:
            registration.PASSWORD_SEMAPHORE.release()
        return h.send_json(200 if ok else 400,
             {"status":"password_updated","next":"/account/client/"} if ok
             else {"error":"Reset link expired or already used."})
    if path not in ("/account/api/account/resend","/account/api/account/password/request"):
        return h.send_json(404,{"error":"Not found."})
    email=x.get("email","")
    if not isinstance(email,str) or len(email)>254 or not registration.EMAIL_RE.fullmatch(email.strip()):
        return h.send_json(422,{"error":"Enter a valid email address."})
    if set(x)!={"email"}:
        return h.send_json(422,{"error":"Invalid request."})
    ip=h.headers.get("X-APEX-Client-IP","")
    if not re.fullmatch(r"[0-9a-fA-F:.]{3,75}",ip):
        return h.send_json(403,{"error":"Secure client route required."})
    now=int(time.time()); digest=registration.ip_digest(ip)
    purpose="verify" if path.endswith("/resend") else "reset"
    with registration.connect() as c:
        c.execute("BEGIN IMMEDIATE")
        c.execute("""DELETE FROM email_rate_events WHERE created_at<?""",(now-86400,))
        count=c.execute("""SELECT COUNT(*) FROM email_rate_events
              WHERE ip_hmac=? AND created_at>?""",(digest,now-3600)).fetchone()[0]
        if count>=10:
            c.execute("ROLLBACK")
            return h.send_json(429,{"error":"Too many email requests. Try again later."})
        c.execute("INSERT INTO email_rate_events(ip_hmac,created_at) VALUES(?,?)",(digest,now))
        row=c.execute("SELECT id,status FROM accounts WHERE email=?",
                      (email.strip().casefold(),)).fetchone()
        if row and (purpose=="reset" and row[1] in ("approved","pending_review") or
                    purpose=="verify" and row[1]=="pending_review"):
            account_flow.enqueue(c,row[0],purpose,now)
        c.execute("COMMIT")
    return h.send_json(200,{"status":"request_accepted",
           "message":"If this account is eligible, an email will arrive shortly."})
