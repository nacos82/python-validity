#!/usr/bin/env python3
"""Repeatedly verify a fingerprint against open-fprintd and tally the results."""
import getpass
import sys

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

TRIES = int(sys.argv[1]) if len(sys.argv) > 1 else 10

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()
manager = dbus.Interface(
    bus.get_object("net.reactivated.Fprint", "/net/reactivated/Fprint/Manager"),
    "net.reactivated.Fprint.Manager",
)
path = manager.GetDefaultDevice()
device = dbus.Interface(
    bus.get_object("net.reactivated.Fprint", path), "net.reactivated.Fprint.Device"
)
user = getpass.getuser()
loop = GLib.MainLoop()
results = []
retries = 0


def on_status(result, done):
    global retries
    if result in ("verify-retry-scan", "verify-swipe-too-short",
                  "verify-finger-not-centered", "verify-remove-and-retry"):
        retries += 1
        return
    if not done:
        return
    results.append(result)
    print(f"  result: {result} ({retries} retry hints first)")
    device.VerifyStop()
    loop.quit()


bus.add_signal_receiver(on_status, signal_name="VerifyStatus",
                        dbus_interface="net.reactivated.Fprint.Device")

device.Claim(user)
try:
    for i in range(1, TRIES + 1):
        input(f"Attempt {i}/{TRIES}: lift your finger, press Enter, then place it ")
        retries = 0
        device.VerifyStart("any")
        # cancelling a scan that is still waiting for a finger crashes the driver
        GLib.timeout_add_seconds(60, loop.quit)
        loop.run()
        try:
            device.VerifyStop()
        except dbus.DBusException:
            pass
finally:
    device.Release()

matches = results.count("verify-match")
print(f"\n{matches} matches out of {len(results)} completed attempts")
