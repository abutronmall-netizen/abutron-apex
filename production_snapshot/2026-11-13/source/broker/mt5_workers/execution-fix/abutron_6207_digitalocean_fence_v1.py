#!/usr/bin/env python3
"""Read-only DigitalOcean provider-side source deletion/absence check.

Requires owner-installed root-only DigitalOcean token with account:read and
droplet:read scopes. Never outputs tokens, enables trading, or submits orders.
"""
from __future__ import annotations
import datetime as dt,hashlib,json,os,stat,tempfile,urllib.request,urllib.error
from pathlib import Path

TOKEN=Path('/etc/abutron/credentials/digitalocean-readonly.token')
OUTPUT=Path('/var/lib/abutron-6207-pilot/digitalocean-source-absent-v1.json')
TEAM='89ae7096-be2b-4c30-a779-52f6116e7c4c'
OLD_NAME='abutron-ai'
OLD_IP='144.126.232.85'
API='https://api.digitalocean.com'
SCHEMA='abutron.6207.digitalocean.source_absent.v1'
class Blocked(RuntimeError):pass

def credential():
    if TOKEN.is_symlink() or not TOKEN.is_file():raise Blocked('DIGITALOCEAN_READONLY_TOKEN_MISSING')
    st=TOKEN.stat()
    if st.st_uid!=0 or stat.S_IMODE(st.st_mode)&0o077 or not 15<st.st_size<400:
        raise Blocked('DIGITALOCEAN_TOKEN_OWNER_OR_PERMISSIONS_INVALID')
    token=TOKEN.read_text().strip()
    if not token.startswith(('dop_v1_','doo_v1_')):raise Blocked('DIGITALOCEAN_TOKEN_FORMAT_INVALID')
    return token

def api_get(path,token):
    if not path.startswith('/v2/') or '?' in path and not path.startswith('/v2/droplets?'):
        raise Blocked('UNAPPROVED_DIGITALOCEAN_API_PATH')
    req=urllib.request.Request(API+path,headers={'Authorization':'Bearer '+token,
      'Accept':'application/json','User-Agent':'ABUTRON6207-SourceFence-ReadOnly/1'},method='GET')
    try:
        with urllib.request.urlopen(req,timeout=5) as response:
            if response.status!=200:raise Blocked('DIGITALOCEAN_PROVIDER_HTTP_NOT_OK')
            raw=response.read(2000000)
            if len(raw)>=2000000:raise Blocked('DIGITALOCEAN_API_RESPONSE_TOO_LARGE')
            result=json.loads(raw)
    except (urllib.error.URLError,TimeoutError,OSError,ValueError) as exc:
        raise Blocked('DIGITALOCEAN_API_CHECK_UNAVAILABLE') from exc
    if not isinstance(result,dict):raise Blocked('DIGITALOCEAN_API_RESPONSE_SCHEMA_INVALID')
    return result

def addr_ips(row):
    networks=row.get('networks',{}).get('v4',[])
    return [str(item.get('ip_address')) for item in networks if isinstance(item,dict)]

def inspect_provider(token=None):
    if token is None:token=credential()
    account=api_get('/v2/account',token).get('account',{})
    team=account.get('team',{}) if isinstance(account,dict) else {}
    if not isinstance(team,dict) or team.get('uuid')!=TEAM:
        raise Blocked('DIGITALOCEAN_TEAM_ACCOUNT_MISMATCH')
    if account.get('email_verified') is not True or account.get('status')!='active':
        raise Blocked('DIGITALOCEAN_TEAM_ACCOUNT_NOT_VERIFIED_ACTIVE')
    seen=0
    all_count=None
    page_digests=[]
    for page in range(1,31):
        payload=api_get('/v2/droplets?per_page=200&page='+str(page),token)
        rows=payload.get('droplets')
        meta=payload.get('meta')
        if not isinstance(rows,list) or not isinstance(meta,dict) or type(meta.get('total')) is not int:
            raise Blocked('DIGITALOCEAN_INVENTORY_NOT_EXHAUSTIVE')
        if all_count is None:all_count=meta['total']
        if all_count!=meta['total'] or all_count<0:
            raise Blocked('DIGITALOCEAN_INVENTORY_CHANGED_DURING_SCAN')
        page_digests.append(hashlib.sha256(json.dumps(rows,sort_keys=True).encode()).hexdigest())
        for row in rows:
            if not isinstance(row,dict):raise Blocked('DIGITALOCEAN_DROPLET_SCHEMA_INVALID')
            if row.get('name')==OLD_NAME or OLD_IP in addr_ips(row):
                raise Blocked('OLD_SOURCE_DROPLET_STILL_EXISTS')
        seen+=len(rows)
        if seen==all_count:break
        if not rows or seen>all_count or page==30:
            raise Blocked('DIGITALOCEAN_INVENTORY_INCOMPLETE')
    if seen!=all_count:raise Blocked('DIGITALOCEAN_INVENTORY_COUNT_MISMATCH')
    now=dt.datetime.now(dt.timezone.utc)
    return {'schema':SCHEMA,'provider':'DigitalOcean',
      'verified_at_utc':now.isoformat(),
      'expires_at_utc':(now+dt.timedelta(minutes=5)).isoformat(),
      'verification':'AUTHENTICATED_DIGITALOCEAN_TEAM_API_FULL_DROPLET_INVENTORY',
      'team_uuid':TEAM,'source_droplet_name':OLD_NAME,'source_original_ipv4':OLD_IP,
      'source_present':False,'droplets_in_account':all_count,'pages_scanned':len(page_digests),
      'inventory_sha256':hashlib.sha256(('|'.join(page_digests)).encode()).hexdigest(),
      'account_uuid_sha256':hashlib.sha256(str(account.get('uuid')).encode()).hexdigest()}

def save(payload):
    OUTPUT.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if OUTPUT.is_symlink():raise Blocked('EVIDENCE_OUTPUT_SYMLINK')
    fd,tmp=tempfile.mkstemp(prefix='.do-source-',dir=OUTPUT.parent)
    try:
        with os.fdopen(fd,'w') as o:
            json.dump(payload,o,indent=2);o.write('\n');o.flush();os.fsync(o.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,OUTPUT)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def main():
    if os.geteuid()!=0:raise SystemExit('ROOT_REQUIRED')
    doc=inspect_provider()
    save(doc)
    print('DIGITALOCEAN_SOURCE_ABSENCE_VERIFIED','TEAM_BOUND',True,
      'PAGES',doc['pages_scanned'],'SOURCE_PRESENT',False,'ORDERS_SUBMITTED',0)
if __name__=='__main__':main()
