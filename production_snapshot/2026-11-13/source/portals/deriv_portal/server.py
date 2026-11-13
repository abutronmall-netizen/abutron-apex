"""APEX-owned, SSH-only Deriv MT5 DEMO portal backend.

Uses QuantDinger's existing JWT-validated /api/auth/info endpoint.
No credential database, no trading function, and no network listening port.
"""
from http.server import BaseHTTPRequestHandler
import json
import os
from pathlib import Path
import re
import socketserver
import subprocess
import threading
import time
from urllib.request import Request, urlopen
from urllib.parse import urlsplit
from urllib.error import HTTPError, URLError
from accounts import list_profiles, save_profile, delete_profile

ROOT = Path("/opt/apex/deriv-portal")
SOCKET = "/run/apex-deriv/portal.sock"
PYTHON = "/home/apexmt5/bridge-runtime/python311/python.exe"
RUNNER = str(ROOT / "mt5_runner.py")
WINE = "/opt/wine-staging/bin/wine"
LOCK = threading.Lock()
ATTEMPTS = []
STATE = {"login": None, "connected": False, "requested": False, "server": None}

class Handler(BaseHTTPRequestHandler):
    server_version = "ApexDerivPortal"
    sys_version = ""
    def log_message(self, format, *args):
        # Never log user input, request bodies, passwords or tokens.
        return

    def reply(self, code, data, content_type="application/json; charset=utf-8"):
        if content_type.startswith("application/json"):
            body = json.dumps(data, separators=(",", ":")).encode()
        else:
            body = data
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, max-age=0")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Frame-Options", "SAMEORIGIN")
        self.send_header("Content-Security-Policy",
                         "default-src 'none'; script-src 'self'; style-src 'self'; "
                         "connect-src 'self'; img-src 'self'; base-uri 'none'; "
                         "form-action 'self'; frame-ancestors 'self'")
        self.end_headers()
        self.wfile.write(body)

    def authenticated(self):
        auth = self.headers.get("Authorization", "")
        if not auth.startswith("Bearer ") or len(auth) > 4096:
            self.reply(401, {"ok": False, "error": "Sign in to APEX first"})
            return False
        try:
            request = Request("http://127.0.0.1:5000/api/auth/info",
                              headers={"Authorization": auth}, method="GET")
            with urlopen(request, timeout=6) as response:
                profile = json.load(response)
            data = profile.get("data") or {}
            role = data.get("role") or {}
            if profile.get("code") != 1 or role.get("id") != "admin":
                self.reply(403, {"ok": False, "error": "APEX administrator access required"})
                return False
            if data.get("must_change_initial_password"):
                self.reply(403, {"ok": False, "error": "Change your APEX initial password first"})
                return False
            return True
        except (HTTPError, URLError, ValueError, TimeoutError):
            self.reply(401, {"ok": False, "error": "APEX authentication unavailable or expired"})
            return False

    def run_mt5(self, packet, timeout=43):
        env = os.environ.copy()
        env.update({"HOME": "/home/apexmt5", "USER": "apexmt5",
                    "WINEPREFIX": "/home/apexmt5/.mt5",
                    "WINEARCH": "win64", "WINEDEBUG": "-all",
                    "DISPLAY": ":1", "LIBGL_ALWAYS_SOFTWARE": "1"})
        try:
            executable = (["/usr/bin/python3", str(ROOT / "mt5_gui_connect.py")]
                          if packet.get("action") == "connect" else [WINE, PYTHON, RUNNER])
            proc = subprocess.run(executable,
                                  cwd="/home/apexmt5/mt5-work",
                                  env=env, input=json.dumps(packet) + "\n",
                                  text=True, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL,
                                  timeout=timeout, check=False)
            max_output = 196608 if packet.get("action") == "history" else 16384
            if proc.returncode != 0 or len(proc.stdout) > max_output:
                return {"ok": False, "error": "MT5 runtime unavailable"}
            raw = proc.stdout.strip().splitlines()
            value = json.loads(raw[-1]) if raw else {}
            if not isinstance(value, dict) or type(value.get("ok")) is not bool:
                raise ValueError("bad response")
            return value
        except (OSError, ValueError, subprocess.TimeoutExpired):
            return {"ok": False, "error": "MT5 connection unavailable. Check the terminal."}

    def do_GET(self):
        path = urlsplit(self.path).path
        if path in ("/", "/index.html"):
            return self.reply(200, (ROOT / "static/index.html").read_bytes(), "text/html; charset=utf-8")
        if path == "/app.js":
            return self.reply(200, (ROOT / "static/app.js").read_bytes(), "application/javascript; charset=utf-8")
        if path == "/menu.js":
            return self.reply(200, (ROOT / "static/menu.js").read_bytes(), "application/javascript; charset=utf-8")
        if path == "/style.css":
            return self.reply(200, (ROOT / "static/style.css").read_bytes(), "text/css; charset=utf-8")
        if path == "/health":
            return self.reply(200, {"ok": True, "mode": "DEMO_ONLY", "orders_enabled": False})
        if path == "/api/accounts":
            if not self.authenticated():
                return
            with LOCK:
                return self.reply(200, {"ok": True, "accounts": list_profiles(),
                                        "simultaneous_mt5_sessions": 1,
                                        "orders_enabled": False})
        if path == "/api/history":
            if not self.authenticated():
                return
            from urllib.parse import parse_qs
            params = parse_qs(urlsplit(self.path).query, keep_blank_values=True)
            requested = params.get("days", ["30"])
            if len(requested) != 1 or requested[0] not in ("7", "30", "90"):
                return self.reply(400, {"ok": False, "error": "Choose 7, 30 or 90 days"})
            days = int(requested[0])
            with LOCK:
                # Read the active MT5 terminal and independently match the
                # broker-confirmed DEMO account to an authorized saved profile.
                result = self.run_mt5({"action": "history", "days": days}, timeout=30)
                account = result.get("data") if result.get("ok") else None
                matched = (isinstance(account, dict)
                    and account.get("mode") == "DEMO"
                    and account.get("trading_execution_enabled") is False
                    and any(str(account.get("login")) == p["login"]
                            and str(account.get("server", "")).lower() == p["server"].lower()
                            for p in list_profiles()))
                if not matched:
                    return self.reply(503, {
                        "ok": False,
                        "error": "Broker history unavailable or account not verified",
                        "orders_enabled": False
                    })
                from datetime import datetime, timezone
                return self.reply(200, {
                    "ok": True, "verified": True,
                    "history": account,
                    "verified_at": datetime.now(timezone.utc).isoformat(),
                    "orders_enabled": False
                })
        if path == "/api/status":
            if not self.authenticated():
                return
            with LOCK:
                # Always check the actual terminal. Never trust a previous
                # login-request flag or a cached success as broker evidence.
                result = self.run_mt5({"action": "status"}, timeout=20)
                account = result.get("data") if result.get("ok") else None
                profiles = list_profiles()
                matched = (isinstance(account, dict)
                    and account.get("mode") == "DEMO"
                    and account.get("trading_execution_enabled") is False
                    and any(str(account.get("login")) == p["login"]
                            and str(account.get("server", "")).lower() == p["server"].lower()
                            for p in profiles))
                if matched:
                    STATE.update({"connected": True, "requested": False,
                                  "login": str(account["login"]), "server": account["server"]})
                    from datetime import datetime, timezone
                    return self.reply(200, {
                        "ok": True, "connected": True, "verified": True,
                        "account": account,
                        "verified_at": datetime.now(timezone.utc).isoformat(),
                        "orders_enabled": False
                    })
                # Mismatched, disconnected, non-DEMO or unreadable sessions
                # must not surface an account or stale financial information.
                STATE["connected"] = False
                return self.reply(200, {
                    "ok": True, "connected": False, "verified": False,
                    "requested": STATE["requested"],
                    "requested_login": STATE["login"] if STATE["requested"] else None,
                    "requested_server": STATE["server"] if STATE["requested"] else None,
                    "account": None, "orders_enabled": False
                })
        return self.reply(404, {"ok": False, "error": "Not found"})

    def do_POST(self):
        path = urlsplit(self.path).path
        if path not in ("/api/connect", "/api/accounts", "/api/accounts/delete"):
            return self.reply(404, {"ok": False, "error": "Not found"})
        if not self.authenticated():
            return
        origin = self.headers.get("Origin", "")
        host = self.headers.get("Host", "")
        if not origin or not host or origin not in ("http://" + host, "https://" + host):
            return self.reply(403, {"ok": False, "error": "Same-origin request required"})
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            return self.reply(415, {"ok": False, "error": "JSON required"})
        try:
            length = int(self.headers.get("Content-Length", "-1"))
            if not 1 <= length <= 2048:
                return self.reply(413, {"ok": False, "error": "Invalid request length"})
            packet = json.loads(self.rfile.read(length))
            if not isinstance(packet, dict):
                raise ValueError("Invalid account request")
            if path in ("/api/accounts", "/api/accounts/delete"):
                with LOCK:
                    login = packet.get("login")
                    server = packet.get("server")
                    if path == "/api/accounts":
                        record = save_profile(login, server, packet.get("label", ""))
                        return self.reply(200, {"ok": True, "account": record,
                                                "orders_enabled": False})
                    deleted = delete_profile(login, server)
                    return self.reply(200, {"ok": True, "deleted": deleted,
                                            "orders_enabled": False})
            login = packet.get("login")
            server = packet.get("server", "")
            password = packet.get("password", "")
            if not isinstance(login, str) or not re.fullmatch(r"[0-9]{4,15}", login):
                raise ValueError("Invalid MT5 account ID")
            if not isinstance(server, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{2,79}", server):
                raise ValueError("Invalid MT5 broker server")
            if not ("deriv" in server.lower() and "demo" in server.lower()):
                raise ValueError("Only Deriv DEMO servers are permitted")
            if not isinstance(password, str) or not 1 <= len(password) <= 160 or any(ord(c) < 32 for c in password):
                raise ValueError("Enter a valid MT5 password")
        except (ValueError, AttributeError, TypeError) as err:
            msg = str(err) if isinstance(err, ValueError) else "Invalid credentials format"
            return self.reply(400, {"ok": False, "error": msg[:110]})
        with LOCK:
            now = time.monotonic()
            ATTEMPTS[:] = [t for t in ATTEMPTS if now - t < 60]
            if len(ATTEMPTS) >= 3:
                return self.reply(429, {"ok": False, "error": "Too many attempts. Try again shortly."})
            ATTEMPTS.append(now)
            STATE.update({"connected": False, "requested": False,
                          "login": None, "server": None})
            label = packet.get("label", "")
            if not isinstance(label, str) or len(label) > 48:
                return self.reply(400, {"ok": False, "error": "Invalid account label"})
            result = self.run_mt5({"action": "connect", "login": int(login),
                                   "server": server, "password": password})
            # Never persist the password, even on successful connection.
            packet.clear()
            password = None
            if result.get("ok") and result.get("requested"):
                save_profile(login, server, label, requested=True)
                STATE.update({"connected": False, "requested": True,
                              "login": login, "server": server})
            return self.reply(202 if result.get("ok") else 422, {
                "ok": bool(result.get("ok")),
                "connected": False, "requested": bool(result.get("requested")),
                "error": result.get("error", ""),
                "message": result.get("message", ""),
                "account": None, "orders_enabled": False
            })

    def do_OPTIONS(self):
        return self.reply(405, {"ok": False, "error": "Method not allowed"})

class UnixServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

if __name__ == "__main__":
    if os.path.exists(SOCKET):
        os.unlink(SOCKET)
    with UnixServer(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o666)
        server.serve_forever(poll_interval=0.25)
