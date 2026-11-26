#!/usr/bin/env python3
"""Mimic pam_fprintd's retry: after a no-match, call VerifyStop and VerifyStart again at once.

Use a wrong finger for each attempt and watch whether the sensor lights up again.
"""
import getpass
import sys
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

TRIES = int(sys.argv[1]) if len(sys.argv) > 1 else 3
WAIT = 30  # seconds per attempt, like pam_fprintd's default timeout

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()
manager = dbus.Interface(
    bus.get_object("net.reactivated.Fprint", "/net/reactivated/Fprint/Manager"),
    "net.reactivated.Fprint.Manager",
)
device = dbus.Interface(
    bus.get_object("net.reactivated.Fprint", manager.GetDefaultDevice()),
    "net.reactivated.Fprint.Device",
)
loop = GLib.MainLoop()
t0 = time.monotonic()
state = {"attempt": 0, "timer": None}


def log(msg):
    print(f"[{time.monotonic() - t0:6.2f}s] {msg}", flush=True)


def start_attempt():
    state["attempt"] += 1
    if state["attempt"] > TRIES:
        loop.quit()
        return False
    log(f"attempt {state['attempt']}/{TRIES}: VerifyStart, place a finger")
    device.VerifyStart("any")
    state["timer"] = GLib.timeout_add_seconds(WAIT, on_timeout)
    return False


def on_timeout():
    log(f"no result within {WAIT}s: the sensor never finished a scan")
    state["timer"] = None
    loop.quit()
    return False


def on_status(result, done):
    log(f"VerifyStatus {result} done={bool(done)}")
    if not done:
        return
    if state["timer"]:
        GLib.source_remove(state["timer"])
        state["timer"] = None
    log("VerifyStop")
    device.VerifyStop()
    if result == "verify-match":
        loop.quit()
        return
    GLib.idle_add(start_attempt)


bus.add_signal_receiver(on_status, signal_name="VerifyStatus",
                        dbus_interface="net.reactivated.Fprint.Device")

device.Claim(getpass.getuser())
try:
    GLib.idle_add(start_attempt)
    loop.run()
finally:
    try:
        device.Release()
    except dbus.DBusException as e:
        log(f"Release failed: {e.get_dbus_name()}")
