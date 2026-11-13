"""APEX Deriv MT5 DEMO GUI login adapter, running as the isolated apexmt5 user.

No EA, no trade/order API, no credential storage, no screenshots of secrets.
Credentials arrive via inherited stdin, are typed only into MT5's verified Login
dialog, and never appear in subprocess command arguments or application logs.
This does NOT independently verify broker authorization (MT5 IPC is unavailable).
"""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time

DISPLAY = ":1"
TERMINAL = "terminal64.exe"
XDOTOOL = "/usr/bin/xdotool"
XWININFO = "/usr/bin/xwininfo"
XPROP = "/usr/bin/xprop"


def report(ok, error="", **extra):
    print(json.dumps({"ok": bool(ok), "error": error, **extra},
                     separators=(",", ":")), flush=True)


def run(command, *, input_text=None, timeout=8, check=True):
    return subprocess.run(command, input=input_text, text=True,
                          stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                          timeout=timeout, check=check)


def xd(*args, input_text=None):
    return run([XDOTOOL, *[str(a) for a in args]],
               input_text=input_text).stdout.strip()


def window_class(win):
    r = run([XPROP, "-id", str(win), "WM_CLASS"]).stdout
    return r.lower()


def geometry(win):
    r = run([XWININFO, "-id", str(win)]).stdout
    result = {}
    for key in ("Absolute upper-left X", "Absolute upper-left Y", "Width", "Height"):
        m = re.search(r"^\s*" + re.escape(key) + r":\s*(-?\d+)\s*$", r, re.M)
        if not m:
            raise RuntimeError("MT5 login window geometry unavailable")
        result[key] = int(m.group(1))
    return (result["Absolute upper-left X"], result["Absolute upper-left Y"],
            result["Width"], result["Height"])


def find_window(title_regex, min_width=0):
    try:
        ids = xd("search", "--onlyvisible", "--name", title_regex).splitlines()
    except subprocess.CalledProcessError:
        return None
    for text in reversed(ids):
        try:
            win = int(text)
            cls = window_class(win)
            x, y, w, h = geometry(win)
            if "terminal64.exe" in cls and w >= min_width and w < 2200:
                return win, x, y, w, h
        except (ValueError, RuntimeError, subprocess.CalledProcessError):
            continue
    return None


def find_dialog():
    found = find_window("^Login$", min_width=450)
    if not found:
        return None
    win, x, y, w, h = found
    # Exact application-specific dialog geometry for MetaTrader 5 build 6295.
    if not (480 <= w <= 570 and 190 <= h <= 255
            and 0 <= x <= 1600 and 0 <= y <= 1100):
        raise RuntimeError("Unexpected MT5 login dialog; refusing to type credentials")
    return found


def ensure_dialog():
    existing = find_dialog()
    if existing:
        return existing
    main = find_window("^MetaTrader 5", min_width=1000)
    if not main:
        raise RuntimeError("MT5 terminal window is not available")
    win, x, y, w, h = main
    # The File menu is at (+18,+9). MT5's Login to Trade Account entry
    # is at (+110,+382) for this verified installed build and theme.
    if not (1150 <= w <= 1600 and 750 <= h <= 1050):
        raise RuntimeError("Unexpected MT5 main window layout")
    xd("windowactivate", "--sync", str(win))
    time.sleep(0.25)
    click(x + 20, y + 9)
    time.sleep(0.30)
    click(x + 110, y + 382)
    for _ in range(15):
        time.sleep(0.25)
        found = find_dialog()
        if found:
            return found
    raise RuntimeError("Could not open MT5 account login dialog")


def click(x, y):
    # Avoid --sync: Wine may delay the motion-complete notification while typing.
    xd("mousemove", x, y)
    xd("click", "1")


def require_login_window(win):
    found = find_dialog()
    if found is None or found[0] != win:
        raise RuntimeError("MT5 account login dialog lost focus")
    current = int(xd("getactivewindow"))
    if current != win:
        raise RuntimeError("MT5 account login dialog is not active")


def type_field(win, x, y, value):
    require_login_window(win)
    click(x, y)
    xd("key", "--clearmodifiers", "ctrl+a")
    xd("key", "--clearmodifiers", "BackSpace")
    # Using stdin avoids exposing the login ID or password in process arguments.
    run([XDOTOOL, "type", "--clearmodifiers", "--delay", "18",
         "--file", "-"], input_text=value, timeout=13)
    require_login_window(win)


def ensure_password_not_saved(x, y):
    # Read ONLY the checkbox pixel. No screenshot is saved, no secret fields read.
    from PIL import ImageGrab
    im = ImageGrab.grab(xdisplay=DISPLAY)
    color = im.getpixel((x + 141, y + 156))
    rgb = color[:3] if isinstance(color, tuple) else (color,) * 3
    if max(rgb) < 100:
        click(x + 141, y + 156)  # Uncheck "Save password for quick login"
        time.sleep(0.25)
        im = ImageGrab.grab(xdisplay=DISPLAY)
        rgb = im.getpixel((x + 141, y + 156))[:3]
    if min(rgb) < 165:
        raise RuntimeError("Unable to confirm that MT5 password saving is disabled")


def main():
    try:
        raw = sys.stdin.readline()
        packet = json.loads(raw)
        action = packet.get("action")
        if action == "probe":
            dialog = ensure_dialog()
            xd("windowactivate", "--sync", dialog[0])
            require_login_window(dialog[0])
            report(True, dialog_ready=True, safe_login_only=True)
            return
        if action != "connect":
            return report(False, "Unsupported MT5 request")
        login = packet.get("login")
        password = packet.get("password")
        server = packet.get("server")
        if not isinstance(login, int) or isinstance(login, bool) or not 1000 <= login < 10**16:
            return report(False, "Invalid MT5 DEMO account number")
        if not isinstance(server, str) or not re.fullmatch(r"(?i)Deriv[A-Za-z0-9._-]{0,65}-Demo(?:-[0-9]{1,3})?", server) or "real" in server.lower():
            return report(False, "Use the exact Deriv DEMO server from Trader's Hub")
        if not isinstance(password, str) or not 1 <= len(password) <= 160 or not password.isascii() or any(ord(c) < 32 for c in password):
            return report(False, "Invalid MT5 password format")
        if os.geteuid() == 0:
            return report(False, "MT5 login adapter must run without root")
        if os.environ.get("DISPLAY") != DISPLAY:
            return report(False, "Private MT5 display is not configured")

        dialog = ensure_dialog()
        win, x, y, w, h = dialog
        xd("windowactivate", "--sync", str(win))
        require_login_window(win)
        ensure_password_not_saved(x, y)
        # Coordinates are relative to the checked, fixed-layout MT5 Login dialog.
        type_field(win, x + 180, y + 75, str(login))
        type_field(win, x + 190, y + 132, server)
        type_field(win, x + 180, y + 103, password)
        password = ""
        packet.clear()
        require_login_window(win)
        click(x + 219, y + 195)  # Login dialog OK, NOT an order-entry control.
        time.sleep(2.5)
        # Do not claim connected: check whether the GUI accepted submission.
        dialog_still_visible = find_dialog() is not None
        if dialog_still_visible:
            return report(False, "MT5 still shows its login dialog. Check DEMO login, password and exact server.")
        return report(True, requested=True, connected=False, submitted=True,
                      message="MT5 login dialog submitted. Broker authentication must still be verified.")
    except Exception:
        # Fail closed; do not echo any payload, terminal metadata or password.
        report(False, "MT5 GUI login could not be completed. Confirm the MT5 window is open and retry.")


if __name__ == "__main__":
    main()
