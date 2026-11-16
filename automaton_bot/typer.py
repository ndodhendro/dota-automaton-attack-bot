"""Type letters with scan codes so Dota's UI accepts them."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_SCANCODE = 0x0008

# US/Indonesian QWERTY set 1 scan codes. No Shift: the game ignores case.
_SCAN = {
    "a": 0x1E, "b": 0x30, "c": 0x2E, "d": 0x20, "e": 0x12, "f": 0x21,
    "g": 0x22, "h": 0x23, "i": 0x17, "j": 0x24, "k": 0x25, "l": 0x26,
    "m": 0x32, "n": 0x31, "o": 0x18, "p": 0x19, "q": 0x10, "r": 0x13,
    "s": 0x1F, "t": 0x14, "u": 0x16, "v": 0x2F, "w": 0x11, "x": 0x2D,
    "y": 0x15, "z": 0x2C,
    "1": 0x02, "2": 0x03, "3": 0x04, "4": 0x05, "5": 0x06,
    "6": 0x07, "7": 0x08, "8": 0x09, "9": 0x0A, "0": 0x0B,
}


class KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    )


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    )


class INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = (("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT))

    _anonymous_ = ("u",)
    _fields_ = (("type", wintypes.DWORD), ("u", _U))


if ctypes.sizeof(ctypes.c_void_p) == 8 and ctypes.sizeof(INPUT) != 40:
    raise RuntimeError(f"Ukuran struktur INPUT tidak terduga: {ctypes.sizeof(INPUT)}")


user32.SendInput.argtypes = (wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int)
user32.SendInput.restype = wintypes.UINT


def _sleep_ms(ms: float) -> None:
    if ms <= 0:
        return
    end = time.perf_counter() + ms / 1000.0
    if ms >= 8:
        time.sleep(max(0.0, (ms - 2) / 1000.0))
    while time.perf_counter() < end:
        pass


def _tap(scan: int, hold_ms: float) -> None:
    down = INPUT(type=INPUT_KEYBOARD, ki=KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE, 0, 0))
    up = INPUT(
        type=INPUT_KEYBOARD,
        ki=KEYBDINPUT(0, scan, KEYEVENTF_SCANCODE | KEYEVENTF_KEYUP, 0, 0),
    )
    sent = user32.SendInput(1, ctypes.byref(down), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())
    _sleep_ms(hold_ms)
    sent = user32.SendInput(1, ctypes.byref(up), ctypes.sizeof(INPUT))
    if sent != 1:
        raise ctypes.WinError(ctypes.get_last_error())


class Typer:
    def __init__(self, hold_ms: float, interval_ms: float, inter_word_ms: float) -> None:
        self.hold_ms = hold_ms
        self.interval_ms = interval_ms
        self.inter_word_ms = inter_word_ms
        self.words = 0
        self.chars = 0

    def type_word(self, text: str) -> int:
        typed = 0
        for ch in text:
            scan = _SCAN.get(ch)
            if scan is None:
                continue
            if typed:
                _sleep_ms(self.interval_ms)
            _tap(scan, self.hold_ms)
            typed += 1
        self.words += 1
        self.chars += typed
        _sleep_ms(self.inter_word_ms)
        return typed


def foreground_is_us() -> bool:
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return False
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value == ctypes.windll.kernel32.GetCurrentProcessId()


def mouse_in_failsafe_corner() -> bool:
    point = wintypes.POINT()
    if not user32.GetCursorPos(ctypes.byref(point)):
        return False
    return point.x <= 3 and point.y <= 3
