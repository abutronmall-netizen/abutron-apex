#!/usr/bin/python3
"""Repair WebRequest URL only inside authenticated Deriv DEMO 7593 Xvfb.

No trading calls, credentials, client-switch updates or broker API writes.
MT5's portable profile is recreated at each worker restart; this operation
restores the 127.0.0.1 CRM allowlist via the MT5 Experts options GUI.
Fail closed on changed window geometry or uncertain interface state.
"""
from __future__ import annotations
import argparse, json, os, re, subprocess, sys, time
from pathlib import Path
from PIL import ImageGrab

CID="9568525eee306da891258ad98c654919"
LOGIN="6357593"
URL="http://127.0.0.1:19745"
SOCKET_HOST="127.0.0.1"
WINDOW_PREFIX="6357593 - Deriv-Demo:"
GEOMETRY=(1280,800)

def cmd(*args, timeout=6):
    p=subprocess.run(("/usr/bin/xdotool",)+args,capture_output=True,
                     text=True,check=False,timeout=timeout)
    if p.returncode:raise RuntimeError("X11_TOOL_ERROR")
    return p.stdout.strip()

def click(x,y,twice=False):
    cmd("mousemove",str(x),str(y))
    cmd("click","--repeat","2","--delay","110","1") if twice else cmd("click","1")

def cap_ready(path,nonce):
    try:
        if path.is_symlink() or not path.is_file():return False
        if not -2 <= time.time()-path.stat().st_mtime <= 15:return False
        lines=path.read_text(encoding="utf-8-sig").splitlines()
        return (len(lines)==10 and
          lines[:5]==["APEX_NATIVE_REVISION_FENCED_CAPABILITY_V4",
                       nonce,LOGIN,"Deriv-Demo","DEMO"] and
          lines[7]=="0.10" and lines[8]=="OFF_REVISION_CHECK_AT_CONSUME" and
          lines[9]=="LIVE_FORBIDDEN" and lines[5].isdigit())
    except (OSError,UnicodeError,ValueError):return False

def count_pixels(image,x,y,predicate):
    return sum(bool(predicate(image.getpixel((xx,yy))[:3]))
               for xx in range(x-7,x+8) for yy in range(y-7,y+8))

def checked(image):
    return count_pixels(image,383,488,lambda p:max(p)<150)>=5

def green(image,x,y):
    return count_pixels(image,x,y,
        lambda p:p[1]>p[0]*1.25 and p[1]>p[2]*1.25 and p[1]>60)

def blue(image,x,y):
    return count_pixels(image,x,y,
        lambda p:p[2]>p[0]*1.3 and p[2]>p[1]*1.1 and p[2]>65)

def screenshot():
    im=ImageGrab.grab()
    if im.size!=GEOMETRY:raise RuntimeError("UNEXPECTED_ISOLATED_MT5_X_GEOMETRY")
    return im

def options_tab(win):
    cmd("windowfocus",win)
    cmd("key","--clearmodifiers","ctrl+o")
    time.sleep(.65)
    click(513,297)
    time.sleep(.25)
    im=screenshot()
    if not (blue(im,403,518)>=7 or green(im,403,518)>=7):
        # A MetaTrader LiveUpdate pop-up can mask Options on a fresh boot.
        cmd("key","Escape")
        click(700,460)  # "Later" on the non-trading LiveUpdate notification
        time.sleep(.35)
        cmd("windowfocus",win)
        cmd("key","--clearmodifiers","ctrl+o")
        time.sleep(.65)
        click(513,297)
        time.sleep(.25)
        im=screenshot()
    if not (blue(im,403,518)>=7 or green(im,403,518)>=7):
        raise RuntimeError("MT5_EXPERTS_OPTIONS_NOT_IDENTIFIED")
    # The DLL import permission must remain unchecked for this account.
    if count_pixels(im,383,463,lambda p:max(p)<150)>=5:
        raise RuntimeError("UNEXPECTED_DLL_IMPORTS_ENABLED")
    return im

def repair(win, *,audit_only):
    im=options_tab(win)
    prev_checked=checked(im)
    first_has_url=blue(im,403,518)>=7
    first_has_plus=green(im,403,518)>=7
    second_has_plus=green(im,403,540)>=7
    second_has_host=blue(im,403,540)>=7
    if first_has_url and not (second_has_plus or second_has_host):
        raise RuntimeError("URL_LIST_UI_NOT_CONSISTENT")
    if not first_has_url and not first_has_plus:
        raise RuntimeError("UNKNOWN_WEBREQUEST_LIST_STATE")
    if audit_only:
        cmd("key","Escape")
        return dict(state="AUDIT_ONLY",was_checked=prev_checked,
                    first_url_row_present=first_has_url,
                    bare_host_entry_present=second_has_host,
                    second_row_add_available=second_has_plus)
    if not prev_checked:
        click(383,488)
        time.sleep(.25)
        if not checked(screenshot()):raise RuntimeError("WEBREQUEST_ENABLE_DID_NOT_STICK")
    if first_has_plus:
        click(510,518,twice=True)
        time.sleep(.20)
        cmd("type","--clearmodifiers","--delay","12",URL,timeout=8)
        cmd("key","Return")
        time.sleep(.3)
        im=screenshot()
        if not blue(im,403,518)>=7 or not green(im,403,540)>=7:
            raise RuntimeError("WEBREQUEST_URL_NOT_SHOWN_AS_ENTRY")
        result="NEW_ALLOWLIST_URL_ENTERED"
    else:
        result="EXISTING_URL_ROW_RETAINED"
    # MQL5 SocketConnect expects the bare host in the same MT5 allowlist;
    # WebRequest GET needs the port-qualified URL above. Preserve both.
    im=screenshot()
    if green(im,403,540)>=7 and blue(im,403,518)>=7:
        click(510,540,twice=True)
        time.sleep(.20)
        cmd("type","--clearmodifiers","--delay","12",SOCKET_HOST,timeout=8)
        cmd("key","Return")
        time.sleep(.3)
        im=screenshot()
        if blue(im,403,540)<7:
            cmd("key","Escape")
            raise RuntimeError("SOCKET_BARE_HOST_NOT_SHOWN_AS_ENTRY")
    elif blue(im,403,540)<7:
        cmd("key","Escape")
        raise RuntimeError("SOCKET_HOST_ROW_NOT_VERIFIED")
    click(760,653)  # OK: persist Options to this isolated portable terminal
    return dict(state=result,was_checked=prev_checked,
                first_url_row_present=first_has_url,
                url_exact=URL if result=="NEW_ALLOWLIST_URL_ENTERED" else None)

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--nonce",required=True)
    parser.add_argument("--audit-gui",action="store_true")
    args=parser.parse_args()
    nonce=args.nonce
    if not re.fullmatch(r"[0-9a-f]{32}",nonce):raise RuntimeError("WORKER_NONCE_INVALID")
    state=Path(os.environ.get("STATE_DIRECTORY",""))
    if state.name!="abutron-client-mt5-"+CID:
        raise RuntimeError("NOT_ISOLATED_7593_WORKER")
    health=json.loads((state/"worker-health.json").read_text())
    if (health.get("id")!=CID or health.get("nonce")!=nonce or
        health.get("broker")!="Deriv" or health.get("server")!="Deriv-Demo" or
        health.get("mode")!="DEMO" or health.get("status")!="CONNECTED"):
        raise RuntimeError("UNVERIFIED_MT5_ACCOUNT_OR_SESSION")
    path=state/"terminal/MQL5/Files"/("ABUTRON_APEX_NATIVE_V4_CAPABILITY_"+nonce+".txt")
    if not os.environ.get("DISPLAY") or not os.environ.get("XAUTHORITY"):
        raise RuntimeError("MISSING_ISOLATED_XVFB_AUTHORITY")
    if tuple(int(x) for x in cmd("getdisplaygeometry").split())!=GEOMETRY:
        raise RuntimeError("UNEXPECTED_XVFB_SIZE")
    ids=cmd("search","--onlyvisible","--name",WINDOW_PREFIX).splitlines()
    matches=[win for win in ids if cmd("getwindowname",win).startswith(WINDOW_PREFIX)]
    if len(matches)!=1:raise RuntimeError("UNEXPECTED_MT5_WINDOW_ACCOUNT_OR_COUNT")
    outcome=repair(matches[0],audit_only=args.audit_gui)
    if args.audit_gui:
        print(json.dumps(outcome,sort_keys=True));return 0
    for _ in range(10):
        if cap_ready(path,nonce):
            print(json.dumps(dict(state="NATIVE_CAPABILITY_VERIFIED_AFTER_GUI",capability=True,
                                  url_edited=outcome["state"]=="NEW_ALLOWLIST_URL_ENTERED"),
                             sort_keys=True))
            return 0
        time.sleep(1)
    print(json.dumps(dict(state="URL_CONFIGURED_BUT_NO_NATIVE_CAPABILITY",
                          capability=False,gui_result=outcome["state"]),sort_keys=True))
    return 3

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        # Never log MT5 credentials or any environment values.
        print(json.dumps(dict(state="FAIL_CLOSED",reason=type(exc).__name__+":"+str(exc)[:100])))
        sys.exit(2)
