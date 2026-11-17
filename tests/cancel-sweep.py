#!/usr/bin/env python3
"""Cancel a verify at increasing delays to hit the on-chip match, and report whether the driver survives."""
import getpass
import glob
import os
import subprocess
import sys
import time

import dbus
import dbus.mainloop.glib
from gi.repository import GLib

DELAYS = [0.3, 0.5, 0.7, 0.9, 1.1, 1.3, 1.5]

dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
bus = dbus.SystemBus()
user = getpass.getuser()
last = []


def driver_pid():
    return subprocess.run(["systemctl", "show", "python3-validity", "-p", "MainPID", "--value"],
                          capture_output=True, text=True).stdout.strip()


# The sensor gets a new device number each time it drops off the USB bus and comes back
def sensor_devnum():
    for path in glob.glob("/sys/bus/usb/devices/*/idProduct"):
        if open(path).read().strip() == "0097":
            return open(os.path.dirname(path) + "/devnum").read().strip()
    return "gone"


def driver_healthy():
    try:
        manager = dbus.Interface(
            bus.get_object("net.reactivated.Fprint", "/net/reactivated/Fprint/Manager"),
            "net.reactivated.Fprint.Manager")
        device = dbus.Interface(
            bus.get_object("net.reactivated.Fprint", manager.GetDefaultDevice()),
            "net.reactivated.Fprint.Device")
        device.ListEnrolledFingers(user)
        return True
    except dbus.DBusException:
        return False


def on_status(result, done):
    last.append(str(result))


bus.add_signal_receiver(on_status, signal_name="VerifyStatus",
                        dbus_interface="net.reactivated.Fprint.Device")


def pump(seconds):
    loop = GLib.MainLoop()
    GLib.timeout_add(int(seconds * 1000), loop.quit)
    loop.run()


if not driver_healthy():
    sys.exit("The driver is not answering. Restart it first: sudo systemctl restart python3-validity open-fprintd")

failures = 0
for delay in DELAYS:
    input(f"Cancel after {delay}s: rest your finger ON the sensor, then press Enter ")
    del last[:]
    before = (driver_pid(), sensor_devnum())
    try:
        manager = dbus.Interface(
            bus.get_object("net.reactivated.Fprint", "/net/reactivated/Fprint/Manager"),
            "net.reactivated.Fprint.Manager")
        device = dbus.Interface(
            bus.get_object("net.reactivated.Fprint", manager.GetDefaultDevice()),
            "net.reactivated.Fprint.Device")
        device.Claim(user)
        try:
            device.VerifyStart("any")
            pump(delay)
            device.VerifyStop()
        finally:
            device.Release()
    except dbus.DBusException as e:
        print(f"  dbus error: {e.get_dbus_name()}")
    pump(5)
    after = (driver_pid(), sensor_devnum())
    problems = []
    if before[0] != after[0]:
        problems.append("driver RESTARTED")
    if before[1] != after[1]:
        problems.append(f"sensor DROPPED off USB ({before[1]} -> {after[1]})")
    if not driver_healthy():
        problems.append("driver NOT ANSWERING")
    failures += bool(problems)
    print(f"  signals: {last or 'none'}; {', '.join(problems) or 'ok'}")
    if problems and not driver_healthy():
        print("\nStopping: the driver needs a restart before more attempts.")
        break

print(f"\n{failures} failures")
