"""APEX client-side private MT5 broker verifier interface.

Status only. Does not submit a customer password or promote a connection state.
"""
from __future__ import annotations
import json,socket
SOCKET="/run/apex-mt5-private/verify.sock"
SCHEMA="APEX_MT5_PRIVATE_DEMO_V1"

def probe(timeout:float=0.9):
    base={"private_gateway_ready":False,
          "customer_password_login_enabled":False,
          "live_mt5_login_enabled":False,
          "broker_connected":False,
          "trading_authorized":False}
    try:
        with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(SOCKET)
            s.sendall(b'{"op":"ping"}\n')
            raw=s.recv(1600)
        d=json.loads(raw)
        if d.get("schema")!=SCHEMA or d.get("ok") is not True:
            return base
        if d.get("trading_authorized") is not False:return base
        enabled=d.get("verify_enabled") is True
        return {**base,"private_gateway_ready":True,
                "customer_password_login_enabled":enabled,
                "supported_demo_brokers":["Deriv","IC Markets","FP Markets"],
                "broker_connected":False,"trading_authorized":False}
    except (OSError,ValueError,TypeError):
        return base
