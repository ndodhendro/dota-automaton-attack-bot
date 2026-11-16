"""Hotkeys, capture loop, and typing."""

from __future__ import annotations

import argparse
import ctypes
import sys
import time
from ctypes import wintypes
from pathlib import Path

import cv2

from automaton_bot.calibrate import choose_region
from automaton_bot.capture import Screen
from automaton_bot.config import CONFIG_PATH, ROOT, active_region, load_config, save_config
from automaton_bot.tracker import Tracker
from automaton_bot.typer import Typer, foreground_is_us, mouse_in_failsafe_corner
from automaton_bot.vision import highlights, read_highlight
from automaton_bot.words import (
    Lexicon,
    group_phrases,
    normalize,
    remainder_of,
    split_by_danger,
    stuck_tail,
    to_detections,
)

VK = {
    "F7": 0x76,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "END": 0x23,
}

_BANNER = r""" _  _    _         _
| \| |__| |___  __| |
| .` / _` / _ \/ _` |
|_|\_\__,_\___/\__,_|"""


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    args = _parser().parse_args(argv)
    if args.self_test:
        from automaton_bot.selftest import run

        run()
        return 0
    cfg = load_config()
    if args.test_image:
        return _test_image(Path(args.test_image), cfg)
    _prepare_console()
    return _live(cfg)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Automaton Attack typing bot")
    parser.add_argument("--self-test", action="store_true", help="run the logic tests without a screen")
    parser.add_argument("--test-image", type=str, help="test OCR on one screenshot, without typing")
    return parser


def _prepare_console() -> None:
    ctypes.windll.kernel32.SetConsoleTitleW("Dota Automaton Attack Bot")
    kernel = ctypes.windll.kernel32
    mode = wintypes.DWORD()
    stdin = kernel.GetStdHandle(-10)
    if kernel.GetConsoleMode(stdin, ctypes.byref(mode)):
        # Quick Edit membekukan proses kalau console diklik.
        kernel.SetConsoleMode(stdin, (mode.value | 0x0080) & ~0x0040)
    stdout = kernel.GetStdHandle(-11)
    if kernel.GetConsoleMode(stdout, ctypes.byref(mode)):
        kernel.SetConsoleMode(stdout, mode.value | 0x0004)


def _print_banner() -> None:
    print()
    print("\033[90m" + _BANNER + "\033[0m")
    print()


def _live(cfg: dict) -> int:
    screen = Screen()
    region = active_region(cfg, screen.monitor)
    lexicon = Lexicon.load()
    reader = None
    state = {
        "armed": False,
        "preview": False,
        "window": False,
        "region": region,
        "tracker": _new_tracker(cfg),
        "typer": Typer(cfg["key_hold_ms"], cfg["key_interval_ms"], cfg["inter_word_ms"]),
        "lexicon": lexicon,
        "focus_warned": False,
        "started": None,
    }
    keys = _KeyEdge()
    _print_banner()
    print("F8   start or stop typing")
    print("F7   preview detection boxes without typing")
    print("F9   calibrate the area")
    print("F10  save a debug screenshot")
    print("End  exit")
    print("Move the cursor to the top-left corner for an emergency stop")
    print()
    print("Focus on the Dota client, start the mini-game, then press F8.")
    print("Do not switch apps while the bot is typing.")

    try:
        while True:
            events = keys.poll()
            if "END" in events:
                print("Exiting.")
                break
            if "F8" in events:
                state["armed"] = not state["armed"]
                if state["armed"]:
                    state["tracker"] = _new_tracker(cfg)
                    state["started"] = time.perf_counter()
                    state["focus_warned"] = False
                    _close_preview(state)
                    print("TYPING ACTIVE. Focus must stay on Dota.")
                else:
                    _report(state)
                    print("Typing stopped.")
            if "F9" in events:
                was = state["armed"]
                state["armed"] = False
                chosen = choose_region(screen.grab_monitor(), (screen.monitor["left"], screen.monitor["top"]))
                if chosen:
                    cfg["region"] = chosen
                    save_config(cfg)
                    state["region"] = chosen
                    state["tracker"] = _new_tracker(cfg)
                    print(f"Area saved: {chosen['width']}x{chosen['height']} at ({chosen['left']}, {chosen['top']})")
                else:
                    print("Calibration canceled.")
                    state["armed"] = was
            if "F7" in events:
                state["preview"] = not state["preview"]
                print("Preview on." if state["preview"] else "Preview off.")
                if not state["preview"]:
                    _close_preview(state)
            if mouse_in_failsafe_corner() and state["armed"]:
                state["armed"] = False
                _report(state)
                print("Emergency stop. The cursor is in the top-left corner.")

            need_frame = state["armed"] or state["preview"] or "F10" in events
            if not need_frame:
                time.sleep(0.03)
                continue

            frame = screen.grab(state["region"])
            if "F10" in events:
                _dump(frame, None, [], "manual")
                print("Debug image saved in the debug folder.")

            if not state["armed"] and not state["preview"]:
                time.sleep(0.03)
                continue

            if reader is None:
                print("Loading the OCR model. The first run may download a few MB...")
                from automaton_bot.vision import Reader

                reader = Reader()
                print("Model ready.")

            found = _process_frame(frame, reader, lexicon, cfg, state)
            if not found:
                time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        _close_preview(state)
        _report(state)
        screen.close()
    return 0


def _process_frame(frame, reader, lexicon: Lexicon, cfg: dict, state: dict) -> bool:
    height = frame.shape[0]
    blobs = reader.blobs(frame, float(cfg["hud_top_ratio"]))
    cutoff = height * float(cfg["danger_y_ratio"])
    low = [blob for blob in blobs if blob.cy >= cutoff]
    high = [blob for blob in blobs if blob.cy < cutoff]
    low_dets = _recognize(reader, frame, low, lexicon, cfg)
    low_dets.sort(key=lambda det: -det.cy)
    shown = _highlights(reader, frame, cfg) if state["armed"] or state["preview"] else []
    high_dets = _recognize(reader, frame, high, lexicon, cfg) if state["armed"] or state["preview"] else []
    high_dets.sort(key=lambda det: (len(det.text), -det.cy))
    if state["armed"] and _type_corrections(low_dets + high_dets, state, shown):
        return bool(blobs) or bool(high_dets)
    if state["armed"]:
        _type_dets(low_dets, state, shown)
        _type_dets(high_dets, state, shown)
    if state["preview"] and not state["armed"]:
        _show_preview(frame, reader.mask(frame), low_dets + high_dets, state)
    elif state["window"]:
        _close_preview(state)
    return bool(blobs)


def _recognize(reader, frame, blobs, lexicon: Lexicon, cfg: dict):
    if not blobs:
        return []
    try:
        pieces = reader.read_blobs(frame, blobs)
    except Exception as exc:
        print(f"OCR failed: {exc}")
        return []
    return to_detections(
        group_phrases(pieces),
        lexicon,
        float(cfg["min_confidence"]),
        float(cfg["raw_confidence"]),
    )


def _highlights(reader, frame, cfg: dict) -> list[str]:
    try:
        blobs = highlights(frame, float(cfg["hud_top_ratio"]))
    except Exception as exc:
        print(f"Highlight detection failed: {exc}")
        return []
    found: list[str] = []
    for blob in blobs:
        text = read_highlight(reader, frame, blob)
        if normalize(text):
            found.append(text)
    return found


def _tail(det, shown: list[str]) -> str:
    for text in shown:
        tail = remainder_of(det.raw, det.text, text)
        if tail:
            return tail
    return ""


def _correction(track, det, shown: list[str]) -> str:
    if track.pending:
        return track.pending
    highlighted = _tail(det, shown)
    if highlighted:
        return highlighted
    if track.sent:
        return stuck_tail(track.sent, det.text) or ""
    return ""


def _type_corrections(dets, state: dict, shown: list[str]) -> bool:
    """Finish a word the game is still holding before typing anything else."""
    emitted: set[int] = set()
    for det in dets:
        track = state["tracker"].observe(det)
        if track is None or id(track) in emitted:
            continue
        send = _correction(track, det, shown)
        if not send:
            continue
        if not _emit(det, track, send, state, correction=True):
            return True
        return True
    return False


def _emit(det, track, send: str, state: dict, correction: bool) -> bool:
    """Type one string. Return False when typing had to stop."""
    if foreground_is_us():
        if not state["focus_warned"]:
            print("Focus the Dota window. Typing is paused while this console is in the foreground.")
            state["focus_warned"] = True
        return False
    state["focus_warned"] = False
    if correction:
        track.retries = state["tracker"].max_retries
    track.pending = ""
    try:
        state["typer"].type_word(send)
    except OSError as exc:
        print(f"Failed to send keys: {exc}")
        print("If Dota is running as an administrator, run this bot as an administrator too.")
        state["armed"] = False
        return False
    track.sent = send
    state["tracker"].mark_typed(track, correction=correction)
    kind = "lexicon" if det.lexicon else "ocr"
    retry = " retry" if track.retries else ""
    print(f"typed {send:<24} y={int(det.cy):4d}  {det.conf:.2f}  {kind}{retry}")
    if det.conf >= 0.99 and normalize(det.raw) == det.text and send == det.text:
        added = state["lexicon"].remember(det.text, det.conf)
        if added:
            print(f"lexicon + {added}")
    return True


def _type_dets(dets, state: dict, shown: list[str] | None = None) -> None:
    emitted: set[int] = set()
    for det in dets:
        if not state["armed"]:
            return
        if mouse_in_failsafe_corner():
            state["armed"] = False
            _report(state)
            print("Emergency stop. The cursor is in the top-left corner.")
            return
        track = state["tracker"].observe(det)
        if track is None or id(track) in emitted:
            continue
        send = det.text
        if track.typed and track.text != det.text:
            continue
        if not _emit(det, track, send, state, correction=False):
            return
        emitted.add(id(track))


def _show_preview(frame, mask, dets, state: dict) -> None:
    vis = frame.copy()
    tint = cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)
    vis = cv2.addWeighted(vis, 0.75, tint, 0.25, 0)
    for det in dets:
        cv2.rectangle(vis, (det.x, det.y), (det.x + det.w, det.y + det.h), (0, 220, 255), 2)
        cv2.putText(vis, det.text, (det.x, max(16, det.y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2, cv2.LINE_AA)
    window = "Preview Automaton Attack"
    cv2.imshow(window, vis)
    cv2.waitKey(1)
    state["window"] = True


def _close_preview(state: dict) -> None:
    if state["window"]:
        cv2.destroyAllWindows()
        state["window"] = False


def _dump(frame, mask, dets, label: str) -> None:
    folder = ROOT / "debug"
    folder.mkdir(exist_ok=True)
    stamp = time.strftime("%H%M%S")
    cv2.imwrite(str(folder / f"{label}-{stamp}.png"), frame)
    if mask is not None:
        cv2.imwrite(str(folder / f"{label}-{stamp}-mask.png"), mask)
    if dets:
        vis = frame.copy()
        for det in dets:
            cv2.rectangle(vis, (det.x, det.y), (det.x + det.w, det.y + det.h), (0, 220, 255), 2)
        cv2.imwrite(str(folder / f"{label}-{stamp}-boxes.png"), vis)


def _test_image(path: Path, cfg: dict) -> int:
    from automaton_bot.config import DEFAULT_REGION_FRACTION
    from automaton_bot.vision import Reader

    image = cv2.imread(str(path))
    if image is None:
        print(f"Could not open {path}")
        return 1
    height, width = image.shape[:2]
    x1, y1, x2, y2 = DEFAULT_REGION_FRACTION
    left, top = int(x1 * width), int(y1 * height)
    crop = image[top : int(y2 * height), left : int(x2 * width)].copy()
    print(f"Image {width}x{height}, board crop {crop.shape[1]}x{crop.shape[0]} at ({left}, {top})")
    print("Loading the OCR model...")
    reader = Reader()
    lexicon = Lexicon.load()
    started = time.perf_counter()
    blobs = reader.blobs(crop, float(cfg["hud_top_ratio"]))
    print(f"Text blobs: {len(blobs)}")
    pieces = reader.read_blobs(crop, blobs)
    print(f"OCR {time.perf_counter() - started:.2f}s")
    if not pieces:
        print("No text was read.")
    for piece in pieces:
        print(f"  ocr {piece.raw!r:<20} {piece.conf:.2f}  x={piece.x} y={piece.y} {piece.w}x{piece.h}")
    dets = to_detections(group_phrases(pieces), lexicon, float(cfg["min_confidence"]), float(cfg["raw_confidence"]))
    danger, safe = split_by_danger(dets, crop.shape[0], float(cfg["danger_y_ratio"]))
    print("Type order:")
    for det in danger + safe:
        kind = "lexicon" if det.lexicon else "ocr"
        zone = "danger" if det in danger else "safe"
        print(f"  {det.text:<24} {kind:<7} {zone:<6} y={int(det.cy)} conf={det.conf:.2f} raw={det.raw!r}")
    _dump(crop, reader.mask(crop), danger + safe, "test-image")
    print(f"Debug images are in {ROOT / 'debug'}")
    return 0


def _new_tracker(cfg: dict) -> Tracker:
    return Tracker(
        radius=float(cfg["match_radius"]),
        retry_delay=float(cfg["retry_delay_ms"]) / 1000.0,
        max_retries=int(cfg["retries"]),
    )


def _report(state: dict) -> None:
    typer: Typer = state["typer"]
    if not typer.words:
        return
    elapsed = 0.0 if state["started"] is None else max(0.0, time.perf_counter() - state["started"])
    print(f"Session: {typer.words} words, {typer.chars} characters, {elapsed:.1f} seconds.")


class _KeyEdge:
    def __init__(self) -> None:
        self._down: dict[int, bool] = {}

    def poll(self) -> set[str]:
        fired: set[str] = set()
        for name, vk in VK.items():
            held = bool(ctypes.windll.user32.GetAsyncKeyState(vk) & 0x8000)
            if held and not self._down.get(vk, False):
                fired.add(name)
            self._down[vk] = held
        return fired
