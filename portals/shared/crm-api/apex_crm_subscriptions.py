"""Manual APEX subscription lifecycle and renewal audit (no payment collection)."""
import datetime as dt
import json

def utc():return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()
def today():return dt.datetime.now(dt.timezone.utc).date()
def init(c):
 c.execute("""CREATE TABLE IF NOT EXISTS apex_crm_subscription_history(
 id INTEGER PRIMARY KEY AUTOINCREMENT,
 account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
 actor_id TEXT NOT NULL,action TEXT NOT NULL,
 old_record TEXT NOT NULL,new_record TEXT NOT NULL,
 reason TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL)""")
 c.execute("CREATE INDEX IF NOT EXISTS apex_sub_history_owner ON apex_crm_subscription_history(account_id,id DESC)")
def current(c,aid):
 r=c.execute("SELECT plan,currency,amount_minor,billing_interval,status,renewal_on,updated_at FROM apex_crm_subscriptions WHERE account_id=?",(aid,)).fetchone()
 return dict(zip(("plan","currency","amount_minor","billing_interval","status","renewal_on","updated_at"),r)) if r else None
def due_state(status,renewal_on):
 if status not in ("trial","active"):return "inactive"
 if not renewal_on:return "unscheduled"
 d=(dt.date.fromisoformat(renewal_on)-today()).days
 return "overdue" if d<0 else "due_soon" if d<=14 else "scheduled"
def public(c,aid):
 r=current(c,aid)
 if not r:return {"plan":None,"status":"not_assigned","payment_verified":False,"payment_gateway_connected":False}
 return {**r,"renewal_state":due_state(r["status"],r["renewal_on"]),
         "payment_verified":False,"payment_gateway_connected":False,"collection_method":"manual"}
def save_event(c,aid,actor,action,old,new,reason=""):
 c.execute("INSERT INTO apex_crm_subscription_history(account_id,actor_id,action,old_record,new_record,reason,created_at) VALUES(?,?,?,?,?,?,?)",
           (aid,actor,action,json.dumps(old or {},sort_keys=True),json.dumps(new or {},sort_keys=True),reason,utc()))
def history(c,aid=None):
 q="SELECT h.account_id,a.email,h.action,h.reason,h.created_at,h.old_record,h.new_record FROM apex_crm_subscription_history h JOIN accounts a ON a.id=h.account_id"
 params=()
 if aid:q+=" WHERE h.account_id=?";params=(aid,)
 q+=" ORDER BY h.id DESC LIMIT 100"
 return [{"account_id":r[0],"email":r[1],"action":r[2],"reason":r[3],"created_at":r[4],"previous":json.loads(r[5]),"current":json.loads(r[6])} for r in c.execute(q,params)]
def indicators(c):
 states=[due_state(a,b) for a,b in c.execute("SELECT status,renewal_on FROM apex_crm_subscriptions")]
 return {"subscription_due_soon":states.count("due_soon"),"subscription_overdue":states.count("overdue")}
def renew(c,actor,aid,new_date,expected_old,reason,audit):
 old=current(c,aid)
 if old is None:raise ValueError("Create a subscription first.")
 if old["status"] not in ("active","trial") or old["billing_interval"]=="one_time":raise ValueError("Only active/trial recurring subscriptions can renew.")
 if not isinstance(new_date,str):raise ValueError("New renewal date is required.")
 try:new=dt.date.fromisoformat(new_date)
 except ValueError:raise ValueError("Invalid renewal date.")
 if new<=today() or (old["renewal_on"] is not None and new_date<=old["renewal_on"]):raise ValueError("Renewal must move to a later future date.")
 if expected_old!=old["renewal_on"]:raise ValueError("Subscription was updated. Refresh before renewing.")
 if not isinstance(reason,str) or not 5<=len(reason.strip())<=300:raise ValueError("A reason of 5-300 characters is required.")
 c.execute("UPDATE apex_crm_subscriptions SET renewal_on=?,updated_at=? WHERE account_id=?",(new_date,utc(),aid))
 save_event(c,aid,actor,"RENEWAL_DATE_CHANGED",old,current(c,aid),reason.strip())
 audit(c,actor,aid,"SUBSCRIPTION_RENEWAL_DATE_CHANGED",str(old["renewal_on"])+" -> "+new_date)
 return {"saved":True,"renewal_on":new_date,"payment_collected":False,"trading_permissions_changed":False}
