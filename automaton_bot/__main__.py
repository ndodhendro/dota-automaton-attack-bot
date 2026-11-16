import ctypes
import sys

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

from automaton_bot.app import main

if __name__ == "__main__":
    sys.exit(main())
