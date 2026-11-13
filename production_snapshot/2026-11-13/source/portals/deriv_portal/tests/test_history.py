"""Regression checks for APEX live DEMO history API over an ephemeral Unix socket.

Uses a temporary test-only authentication bypass confined to this process.
The production server is never monkeypatched or restarted by this test.
"""
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import threading

sys.path.insert(0, "/opt/apex/deriv-portal")
import server as portal

class UnixConn(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__("localhost", timeout=40)
        self.path = path
    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(self.path)

def fetch(socket_path, uri):
    conn = UnixConn(socket_path)
    try:
        conn.request("GET", uri)
        response = conn.getresponse()
        return response.status, json.loads(response.read())
    finally:
        conn.close()

def main():
    path = "/home/apexmt5/mt5-work/apex-history-validation.sock"
    Path(path).unlink(missing_ok=True)
    portal.Handler.authenticated = lambda self: True
    server = portal.UnixServer(path, portal.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        status, data = fetch(path, "/api/history?days=30")
        assert status == 200 and data["verified"] is True and data["orders_enabled"] is False, (status, data)
        record = data["history"]
        assert record["mode"] == "DEMO" and record["days"] == 30
        assert isinstance(record["deals"], list)
        assert record["trade_executions"] >= record["closing_executions"] >= 0
        assert len(record["deals"]) <= 250
        assert all(entry["entry"] in ("CLOSE","OPEN","CLOSE BY","REVERSE") for entry in record["deals"])
        assert all("password" not in entry and "token" not in entry for entry in record["deals"])
        assert abs(record["net_trading_pnl"] -
                   round(record["gross_realized_profit"] + record["commissions"]
                         + record["swaps"] + record["fees"], 2)) < 0.021
        print("PASS: genuine MT5 history, deal details, P&L and costs, DEMO-only")
        invalid, _ = fetch(path, "/api/history?days=999")
        assert invalid == 400
        print("PASS: unsupported history periods rejected")
        original = portal.list_profiles
        portal.list_profiles = lambda: [{"login": "9999999999", "server": "Deriv-Demo"}]
        denied, denied_data = fetch(path, "/api/history?days=30")
        assert denied == 503 and "history" not in denied_data and "account" not in denied_data
        assert denied_data["orders_enabled"] is False
        portal.list_profiles = original
        print("PASS: mismatched saved profile does not receive account history")
    finally:
        server.shutdown()
        server.server_close()
        Path(path).unlink(missing_ok=True)

if __name__ == "__main__":
    main()
