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
from automaton_bot.words import Lexicon, group_phrases, split_by_danger, to_detections

VK = {
    "F7": 0x76,
    "F8": 0x77,
    "F9": 0x78,
    "F10": 0x79,
    "END": 0x23,
}


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
    parser.add_argument("--self-test", action="store_true", help="jalankan tes logika tanpa layar")
    parser.add_argument("--test-image", type=str, help="uji OCR pada satu screenshot, tanpa mengetik")
    return parser


def _prepare_console() -> None:
    ctypes.windll.kernel32.SetConsoleTitleW("Automaton Attack Bot")
    handle = ctypes.windll.kernel32.GetStdHandle(-10)
    mode = wintypes.DWORD()
    if ctypes.windll.kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
        # Quick Edit membekukan proses kalau console diklik.
        ctypes.windll.kernel32.SetConsoleMode(handle, (mode.value | 0x0080) & ~0x0040)


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
        "focus_warned": False,
        "started": None,
    }
    keys = _KeyEdge()
    print()
    print("Automaton Attack bot siap.")
    print(f"Area: {region['width']}x{region['height']} di ({region['left']}, {region['top']})")
    if cfg.get("region"):
        print(f"Area kalibrasi dipakai dari {CONFIG_PATH.name}.")
    else:
        print("Area default dari screenshot 1920x1080. Tekan F9 kalau kotaknya meleset.")
    print(f"Kamus: {len(lexicon.words)} kata. Kata di luar kamus tetap diketik kalau OCR yakin.")
    print()
    print("F8   mulai / berhenti mengetik")
    print("F7   preview kotak deteksi, tanpa mengetik")
    print("F9   kalibrasi area")
    print("F10  simpan gambar debug")
    print("End  keluar")
    print("Pojok kiri-atas mouse = stop darurat")
    print()
    print("Fokuskan Dota, mulai mini-game, lalu tekan F8.")
    print("Jangan klik jendela console ini saat bot sedang mengetik.")

    try:
        while True:
            events = keys.poll()
            if "END" in events:
                print("Keluar.")
                break
            if "F8" in events:
                state["armed"] = not state["armed"]
                if state["armed"]:
                    state["tracker"] = _new_tracker(cfg)
                    state["started"] = time.perf_counter()
                    state["focus_warned"] = False
                    _close_preview(state)
                    print("MENGETIK AKTIF. Fokus harus di Dota.")
                else:
                    _report(state)
                    print("Mengetik berhenti.")
            if "F9" in events:
                was = state["armed"]
                state["armed"] = False
                chosen = choose_region(screen.grab_monitor(), (screen.monitor["left"], screen.monitor["top"]))
                if chosen:
                    cfg["region"] = chosen
                    save_config(cfg)
                    state["region"] = chosen
                    state["tracker"] = _new_tracker(cfg)
                    print(f"Area disimpan: {chosen['width']}x{chosen['height']} di ({chosen['left']}, {chosen['top']})")
                else:
                    print("Kalibrasi dibatalkan.")
                    state["armed"] = was
            if "F7" in events:
                state["preview"] = not state["preview"]
                print("Preview hidup." if state["preview"] else "Preview mati.")
                if not state["preview"]:
                    _close_preview(state)
            if mouse_in_failsafe_corner() and state["armed"]:
                state["armed"] = False
                _report(state)
                print("Stop darurat. Mouse ada di pojok kiri-atas.")

            need_frame = state["armed"] or state["preview"] or "F10" in events
            if not need_frame:
                time.sleep(0.03)
                continue

            frame = screen.grab(state["region"])
            if "F10" in events:
                _dump(frame, None, [], "manual")
                print("Gambar debug tersimpan di folder debug.")

            if not state["armed"] and not state["preview"]:
                time.sleep(0.03)
                continue

            if reader is None:
                print("Memuat model OCR. Pertama kali bisa mengunduh beberapa MB...")
                from automaton_bot.vision import Reader

                reader = Reader()
                print("Model siap.")

            found = _process_frame(frame, reader, lexicon, cfg, state)
            if not found:
                time.sleep(0.02)
    except KeyboardInterrupt:
        print("\nDihentikan.")
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
    if state["armed"]:
        _type_dets(low_dets, state)
    high_dets = _recognize(reader, frame, high, lexicon, cfg) if state["armed"] or state["preview"] else []
    high_dets.sort(key=lambda det: (len(det.text), -det.cy))
    if state["armed"]:
        _type_dets(high_dets, state)
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
        print(f"OCR gagal: {exc}")
        return []
    return to_detections(
        group_phrases(pieces),
        lexicon,
        float(cfg["min_confidence"]),
        float(cfg["raw_confidence"]),
    )


def _type_dets(dets, state: dict) -> None:
    emitted: set[int] = set()
    for det in dets:
        if not state["armed"]:
            return
        if mouse_in_failsafe_corner():
            state["armed"] = False
            _report(state)
            print("Stop darurat. Mouse ada di pojok kiri-atas.")
            return
        track = state["tracker"].observe(det)
        if track is None or id(track) in emitted:
            continue
        if foreground_is_us():
            if not state["focus_warned"]:
                print("Fokuskan jendela Dota. Ketikan ditunda selama console ini yang di depan.")
                state["focus_warned"] = True
            return
        state["focus_warned"] = False
        try:
            state["typer"].type_word(det.text)
        except OSError as exc:
            print(f"Gagal mengirim tombol: {exc}")
            print("Kalau Dota jalan sebagai administrator, jalankan bot ini sebagai administrator juga.")
            state["armed"] = False
            return
        state["tracker"].mark_typed(track)
        emitted.add(id(track))
        kind = "kamus" if det.lexicon else "ocr"
        retry = " ulang" if track.retries else ""
        print(f"ketik {det.text:<24} y={int(det.cy):4d}  {det.conf:.2f}  {kind}{retry}")


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
        print(f"Tidak bisa membuka {path}")
        return 1
    height, width = image.shape[:2]
    x1, y1, x2, y2 = DEFAULT_REGION_FRACTION
    left, top = int(x1 * width), int(y1 * height)
    crop = image[top : int(y2 * height), left : int(x2 * width)].copy()
    print(f"Gambar {width}x{height}, crop papan {crop.shape[1]}x{crop.shape[0]} pada ({left}, {top})")
    print("Memuat model OCR...")
    reader = Reader()
    lexicon = Lexicon.load()
    started = time.perf_counter()
    blobs = reader.blobs(crop, float(cfg["hud_top_ratio"]))
    print(f"Blob teks: {len(blobs)}")
    pieces = reader.read_blobs(crop, blobs)
    print(f"OCR {time.perf_counter() - started:.2f}s")
    if not pieces:
        print("Tidak ada teks terbaca.")
    for piece in pieces:
        print(f"  ocr {piece.raw!r:<20} {piece.conf:.2f}  x={piece.x} y={piece.y} {piece.w}x{piece.h}")
    dets = to_detections(group_phrases(pieces), lexicon, float(cfg["min_confidence"]), float(cfg["raw_confidence"]))
    danger, safe = split_by_danger(dets, crop.shape[0], float(cfg["danger_y_ratio"]))
    print("Urutan ketik:")
    for det in danger + safe:
        kind = "kamus" if det.lexicon else "ocr"
        zone = "bahaya" if det in danger else "aman"
        print(f"  {det.text:<24} {kind:<6} {zone:<6} y={int(det.cy)} conf={det.conf:.2f} raw={det.raw!r}")
    _dump(crop, reader.mask(crop), danger + safe, "test-image")
    print(f"Gambar debug ada di {ROOT / 'debug'}")
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
    print(f"Sesi: {typer.words} kata, {typer.chars} huruf, {elapsed:.1f} detik.")


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
