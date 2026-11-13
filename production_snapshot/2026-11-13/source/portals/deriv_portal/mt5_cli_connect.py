"""APEX Deriv DEMO MT5 login launcher via official MetaQuotes /config interface.

This helper runs as apexmt5. No trading logic or order methods.
Credentials live in a mode-0600 temporary RAM file only during terminal
startup. MT5's own storage behavior is controlled with KeepPrivate=0.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time

WINE = "/opt/wine-staging/bin/wine"
SERVER = "/home/apexmt5/.mt5/drive_c/Program Files/MetaTrader 5/terminal64.exe"
WINE_SERVER = "/opt/wine-staging/bin/wineserver"

def reply(ok, error="", **extra):
    print(json.dumps({"ok": ok, "error": error, **extra}, separators=(",", ":")), flush=True)

def main():
    try:
        packet=json.loads(sys.stdin.readline())
        login=packet.get("login")
        server=packet.get("server")
        password=packet.get("password")
        if not isinstance(login,int) or isinstance(login,bool) or not 1000<=login<10**16:
            return reply(False,"Invalid MT5 account number")
        if not isinstance(server,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,79}",server):
            return reply(False,"Invalid MT5 broker server")
        if not ("deriv" in server.lower() and "demo" in server.lower()):
            return reply(False,"Only Deriv DEMO servers are permitted")
        if not isinstance(password,str) or not 1<=len(password)<=160 or any(ord(c)<32 for c in password):
            return reply(False,"Invalid MT5 password")
        if not Path(SERVER).is_file():
            return reply(False,"MT5 terminal executable missing")

        # Lock session while authenticating; remove credentials after startup.
        # Never put passwords on command lines, stdout, stderr, or persistent disk.
        ini=("[Common]\r\n"
             f"Login={login}\r\n"
             f"Server={server}\r\n"
             f"Password={password}\r\n"
             "KeepPrivate=0\r\nProxyEnable=0\r\n"
             "[Experts]\r\n"
             "AllowLiveTrading=0\r\nAllowDllImport=0\r\nEnabled=0\r\n"
             "[StartUp]\r\nExpert=\r\n")
        fd,name=tempfile.mkstemp(prefix="apex-deriv-",suffix=".ini",dir="/dev/shm")
        try:
            os.fchmod(fd,0o600)
            with os.fdopen(fd,"w",encoding="ascii",newline="") as file:
                file.write(ini)
                file.flush()
                os.fsync(file.fileno())
            ini=""
            # Existing terminal must be restarted to read official /config options.
            subprocess.run([WINE_SERVER,"-k"],stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL,timeout=10,check=False)
            time.sleep(2)
            config="Z:\\dev\\shm\\" + Path(name).name
            proc=subprocess.Popen([WINE, SERVER, "/config:"+config],
                                   stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
                                   stdin=subprocess.DEVNULL,start_new_session=True,
                                   cwd="/home/apexmt5/mt5-work",
                                   env=os.environ.copy())
            time.sleep(13)
            if proc.poll() is not None and proc.returncode not in (0,None):
                return reply(False,"MT5 could not start the DEMO login session")
            # Accept launch only, not account verification. No broker data is invented.
            return reply(True,requested=True,connected=False,
                         message="MT5 DEMO login was requested. Confirm account status in MT5.")
        finally:
            try:
                os.unlink(name)
            except FileNotFoundError:
                pass
    except Exception:
        return reply(False,"MT5 DEMO login could not be started. Check MT5 and your server name.")

if __name__=="__main__":
    main()
