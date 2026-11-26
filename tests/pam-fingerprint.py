#!/usr/bin/env python3
"""Run a PAM service's auth stack (default: gdm-fingerprint) as the current user.

Prints every message PAM sends, with timestamps, so you can see how many
fingerprint tries pam_fprintd gives before it returns. Password prompts get an
empty answer. Set PAM_CONFDIR to read service files from another directory.
"""
import os
import ctypes
import ctypes.util
import getpass
import sys
import time

SERVICE = sys.argv[1] if len(sys.argv) > 1 else "gdm-fingerprint"

libpam = ctypes.CDLL(ctypes.util.find_library("pam"))
libc = ctypes.CDLL(ctypes.util.find_library("c"))
libc.calloc.restype = ctypes.c_void_p
libc.calloc.argtypes = [ctypes.c_size_t, ctypes.c_size_t]
libc.strdup.restype = ctypes.c_void_p
libc.strdup.argtypes = [ctypes.c_char_p]

PAM_STYLES = {1: "PROMPT_ECHO_OFF", 2: "PROMPT_ECHO_ON", 3: "ERROR_MSG", 4: "TEXT_INFO"}


class PamMessage(ctypes.Structure):
    _fields_ = [("msg_style", ctypes.c_int), ("msg", ctypes.c_char_p)]


class PamResponse(ctypes.Structure):
    _fields_ = [("resp", ctypes.c_void_p), ("resp_retcode", ctypes.c_int)]


CONV_FUNC = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_int,
                             ctypes.POINTER(ctypes.POINTER(PamMessage)),
                             ctypes.POINTER(ctypes.POINTER(PamResponse)), ctypes.c_void_p)


class PamConv(ctypes.Structure):
    _fields_ = [("conv", CONV_FUNC), ("appdata_ptr", ctypes.c_void_p)]


t0 = time.monotonic()


def log(text):
    print(f"[{time.monotonic() - t0:6.2f}s] {text}", flush=True)


def conversation(n, msgs, resp, _appdata):
    arr = libc.calloc(n, ctypes.sizeof(PamResponse))
    responses = ctypes.cast(arr, ctypes.POINTER(PamResponse))
    for i in range(n):
        m = msgs[i].contents
        log(f"{PAM_STYLES.get(m.msg_style, m.msg_style)}: {m.msg.decode(errors='replace')}")
        if m.msg_style in (1, 2):
            # Never answer password prompts: this test is about the fingerprint only.
            responses[i].resp = libc.strdup(b"")
    resp[0] = responses
    return 0


conv_cb = CONV_FUNC(conversation)
conv = PamConv(conv_cb, None)
handle = ctypes.c_void_p()
libpam.pam_strerror.restype = ctypes.c_char_p

confdir = os.environ.get("PAM_CONFDIR")
if confdir:
    rc = libpam.pam_start_confdir(SERVICE.encode(), getpass.getuser().encode(), ctypes.byref(conv),
                                  confdir.encode(), ctypes.byref(handle))
else:
    rc = libpam.pam_start(SERVICE.encode(), getpass.getuser().encode(), ctypes.byref(conv),
                          ctypes.byref(handle))
if rc != 0:
    sys.exit(f"pam_start failed: {rc}")
log(f"pam_authenticate with service {SERVICE}")
rc = libpam.pam_authenticate(handle, 0)
log(f"pam_authenticate returned {rc}: {libpam.pam_strerror(handle, rc).decode()}")
libpam.pam_end(handle, rc)
