import ctypes
import sys
import traceback

try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def _hold_on_error() -> None:
    print()
    print("The bot stopped because of the error above.")
    try:
        input("Press Enter to close this window...")
    except EOFError:
        pass


if __name__ == "__main__":
    try:
        from automaton_bot.app import main

        code = main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        if code:
            _hold_on_error()
        sys.exit(code)
    except Exception:
        traceback.print_exc()
        _hold_on_error()
        sys.exit(1)
    sys.exit(code or 0)
