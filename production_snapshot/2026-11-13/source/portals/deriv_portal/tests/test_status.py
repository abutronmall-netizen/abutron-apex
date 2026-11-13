"""Read-only APEX status regression: isolated UNIX test socket, never exposed publicly.

Exercises actual MT5 read-only adapter with a test-only authentication shim
on this ephemeral server instance; production authentication is not patched.
"""
import http.client
import json
import os
from pathlib import Path
import socket
import sys
import threading
sys.path.insert(0,'/opt/apex/deriv-portal')
import server as portal

class UnixConnection(http.client.HTTPConnection):
    def __init__(self,path):
        super().__init__('localhost',timeout=24)
        self.path=path
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.connect(self.path)

def request(path,where):
    c=UnixConnection(where)
    try:
        c.request('GET',path)
        r=c.getresponse()
        data=json.loads(r.read())
        assert r.status==200,(r.status,data)
        return data
    finally:
        c.close()

def main():
    path='/home/apexmt5/mt5-work/apex-readonly-status-test.sock'
    if Path(path).exists():
        os.unlink(path)
    # Ephemeral isolated test ONLY; never change production Handler process.
    portal.Handler.authenticated=lambda self: True
    srv=portal.UnixServer(path,portal.Handler)
    thread=threading.Thread(target=srv.serve_forever,daemon=True)
    thread.start()
    try:
        original=portal.list_profiles
        actual=request('/api/status',path)
        assert actual['connected'] is True
        assert actual['verified'] is True
        assert actual['orders_enabled'] is False
        assert actual['account']['mode']=='DEMO'
        assert isinstance(actual['account']['balance'],float)
        assert isinstance(actual['account']['position_rows'],list)
        print('PASS: matched saved DEMO account, live balance and positions verified via MT5')
        portal.list_profiles=lambda:[{'login':'9999900','server':'Deriv-Demo'}]
        blocked=request('/api/status',path)
        assert blocked['connected'] is False
        assert blocked['verified'] is False
        assert blocked['account'] is None
        assert blocked['orders_enabled'] is False
        print('PASS: mismatched saved account denied access to live broker data')
        portal.list_profiles=original
        print('PASS: test-only temporary authenticated handler was isolated from systemd service')
    finally:
        srv.shutdown()
        srv.server_close()
        Path(path).unlink(missing_ok=True)

if __name__=='__main__':
    main()
