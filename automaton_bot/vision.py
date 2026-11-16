"""Find white and gold labels, then read them."""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from automaton_bot.words import Piece


@dataclass
class Blob:
    x: int
    y: int
    w: int
    h: int

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


class Reader:
    def __init__(self) -> None:
        import logging

        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        try:
            from rapidocr import RapidOCR
        except ImportError:
            from rapidocr_onnxruntime import RapidOCR

        self._ocr = RapidOCR()
        logging.getLogger("RapidOCR").setLevel(logging.ERROR)
        # The first recognition call is much slower than the ones after it.
        blank = np.full((48, 160, 3), 255, np.uint8)
        cv2.putText(blank, "kaya", (8, 34), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 2, cv2.LINE_AA)
        try:
            self._ocr(blank, use_det=False, use_cls=False)
        except Exception:
            pass

    def blobs(self, frame: np.ndarray, hud_top_ratio: float) -> list[Blob]:
        mask = _text_mask(frame)
        height, width = mask.shape
        scale = max(width / 980.0, 0.65)
        kx = max(5, int(round(11 * scale)))
        ky = max(2, int(round(3 * scale)))
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kx, ky))
        joined = cv2.dilate(mask, kernel)
        count, _, stats, _ = cv2.connectedComponentsWithStats(joined, 8)
        # Labels in this mini-game are one short line. Highlights on the
        # automaton and the score header fall outside this band.
        min_h = max(22, int(26 * scale))
        max_h = int(52 * scale)
        found: list[Blob] = []
        hud_cut = height * hud_top_ratio
        for index in range(1, count):
            x, y, w, h = (int(v) for v in stats[index][:4])
            if h < min_h or h > max_h or w < int(22 * scale) or w > int(width * 0.8):
                continue
            if (y + h / 2) < hud_cut:
                continue
            aspect = w / float(h)
            # Short names are a bit wider than they are tall. Solid bars and
            # square highlights on the automaton are not.
            if aspect < 1.15 or aspect > 14:
                continue
            roi = mask[y : y + h, x : x + w]
            if roi.size == 0:
                continue
            fill = float(roi.mean()) / 255.0
            if fill < 0.11 or fill > 0.62:
                continue
            if _ink_runs(roi) < 2:
                continue
            found.append(Blob(x, y, w, h))
        found.sort(key=lambda blob: blob.cy, reverse=True)
        return found[:12]

    def read_blobs(self, frame: np.ndarray, blobs: list[Blob]) -> list[Piece]:
        pieces: list[Piece] = []
        for blob in blobs:
            pieces.extend(self._read_blob(frame, blob))
        return pieces

    def _read_blob(self, frame: np.ndarray, blob: Blob) -> list[Piece]:
        height, width = frame.shape[:2]
        pad_x, pad_y = 6, 3
        x0 = max(0, blob.x - pad_x)
        y0 = max(0, blob.y - pad_y)
        x1 = min(width, blob.x + blob.w + pad_x)
        y1 = min(height, blob.y + blob.h + pad_y)
        crop = frame[y0:y1, x0:x1]
        if crop.size == 0:
            return []
        mask = _text_mask(crop)
        canvas = np.full_like(crop, 255)
        canvas[mask > 0] = (0, 0, 0)
        canvas = cv2.resize(canvas, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
        canvas = cv2.copyMakeBorder(canvas, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=(255, 255, 255))
        try:
            result = self._ocr(canvas, use_det=False, use_cls=False)
        except TypeError:
            result = self._ocr(canvas)
        except Exception:
            return []
        pieces: list[Piece] = []
        for _box, text, score in _rows(result):
            text = str(text).strip()
            if text:
                pieces.append(Piece(raw=text, conf=float(score), x=blob.x, y=blob.y, w=blob.w, h=blob.h))
        return pieces

    def mask(self, frame: np.ndarray) -> np.ndarray:
        return _text_mask(frame)


def _ink_runs(roi: np.ndarray) -> int:
    columns = (roi > 0).any(axis=0)
    runs = 0
    inside = False
    for value in columns:
        if value and not inside:
            runs += 1
            inside = True
        elif not value:
            inside = False
    return runs


def _text_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    # Labels are white or gold. The score HUD is green, so it stays out.
    white = cv2.inRange(hsv, (0, 0, 185), (180, 80, 255))
    gold = cv2.inRange(hsv, (12, 70, 150), (38, 255, 255))
    mask = cv2.bitwise_or(white, gold)
    kernel = np.ones((2, 2), np.uint8)
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)


def _rows(result) -> list[tuple]:
    if result is None:
        return []
    data = result[0] if isinstance(result, tuple) else result
    if data is None:
        return []
    txts = getattr(data, "txts", None)
    if txts is not None:
        boxes = getattr(data, "boxes", None)
        scores = getattr(data, "scores", None)
        rows = []
        for index, text in enumerate(txts):
            box = None if boxes is None or index >= len(boxes) else boxes[index]
            score = 1.0 if scores is None or index >= len(scores) else scores[index]
            rows.append((box, text, score))
        return rows
    if isinstance(data, list):
        rows = []
        for item in data:
            if not item or len(item) < 2:
                continue
            score = float(item[2]) if len(item) > 2 else 1.0
            rows.append((item[0], item[1], score))
        return rows
    return []
