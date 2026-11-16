"""Drag a rectangle around the mini-game board."""

from __future__ import annotations

import cv2
import numpy as np


def choose_region(frame: np.ndarray, origin: tuple[int, int]) -> dict | None:
    height, width = frame.shape[:2]
    scale = min(1.0, 1400 / width, 860 / height)
    state = {"drag": False, "has": False, "x0": 0, "y0": 0, "x1": 0, "y1": 0}

    def on_mouse(event, x, y, _flags, _param) -> None:
        ox = int(x / scale)
        oy = int(y / scale)
        if event == cv2.EVENT_LBUTTONDOWN:
            state.update(drag=True, has=True, x0=ox, y0=oy, x1=ox, y1=oy)
        elif event == cv2.EVENT_MOUSEMOVE and state["drag"]:
            state["x1"] = ox
            state["y1"] = oy
        elif event == cv2.EVENT_LBUTTONUP and state["drag"]:
            state["drag"] = False
            state["x1"] = ox
            state["y1"] = oy

    window = "Kalibrasi Automaton Attack"
    cv2.namedWindow(window, cv2.WINDOW_AUTOSIZE)
    cv2.setMouseCallback(window, on_mouse)
    print("Tarik kotak di sekeliling papan mini-game.")
    print("Enter = simpan, C = hapus kotak, Esc = batal.")

    while True:
        vis = frame.copy()
        if state["has"]:
            x0, x1 = sorted((state["x0"], state["x1"]))
            y0, y1 = sorted((state["y0"], state["y1"]))
            cv2.rectangle(vis, (x0, y0), (x1, y1), (0, 220, 255), 2)
        shown = cv2.resize(vis, (int(width * scale), int(height * scale)), interpolation=cv2.INTER_AREA)
        cv2.imshow(window, shown)
        key = cv2.waitKey(20) & 0xFF
        if key in (13, 10) and state["has"]:
            x0, x1 = sorted((state["x0"], state["x1"]))
            y0, y1 = sorted((state["y0"], state["y1"]))
            if x1 - x0 < 40 or y1 - y0 < 40:
                print("Kotak terlalu kecil.")
                continue
            cv2.destroyWindow(window)
            return {
                "left": origin[0] + x0,
                "top": origin[1] + y0,
                "width": x1 - x0,
                "height": y1 - y0,
            }
        if key in (ord("c"), ord("C")):
            state["has"] = False
        if key == 27:
            cv2.destroyWindow(window)
            return None
