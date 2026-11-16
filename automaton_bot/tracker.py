"""Remember words that were already typed so falling labels are not repeated."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from automaton_bot.words import Det


def _contains(longer: str, shorter: str) -> bool:
    return len(shorter) >= 4 and shorter in longer


@dataclass
class Track:
    text: str
    cx: float
    cy: float
    w: float = 40
    h: float = 20
    conf: float = 1.0
    hits: int = 1
    typed: bool = False
    retries: int = 0
    typed_at: float = 0.0
    last_seen: float = 0.0


class Tracker:
    def __init__(self, radius: float, retry_delay: float, max_retries: int) -> None:
        self.radius = radius
        self.retry_delay = retry_delay
        self.max_retries = max_retries
        self.tracks: list[Track] = []

    def gc(self, now: float) -> None:
        self.tracks = [t for t in self.tracks if now - t.last_seen < 0.55]

    def observe(self, det: Det, now: float | None = None) -> Track | None:
        """Return a track that should be typed, or None.

        Untyped labels are returned again until ``mark_typed``. The caller
        must type a track at most once per frame. A typed label is returned
        again only for a retry, after ``retry_delay``, while it is still visible.
        """
        now = time.perf_counter() if now is None else now
        self.gc(now)
        track = self._match(det)
        if track is None:
            occupied = self._match_place(det)
            if occupied is not None:
                # Two labels are on top of each other. Keep the clean phrase
                # and do not type the mixed OCR result.
                if len(det.text) > len(occupied.text) and det.conf >= occupied.conf and _contains(det.text, occupied.text):
                    occupied.text = det.text
                    occupied.conf = det.conf
                occupied.last_seen = now
                return None
            track = Track(
                text=det.text,
                cx=det.cx,
                cy=det.cy,
                w=det.w,
                h=det.h,
                conf=det.conf,
                hits=1,
                last_seen=now,
            )
            self.tracks.append(track)
            return None
        track.cx = det.cx
        track.cy = det.cy
        track.w = det.w
        track.h = det.h
        track.conf = max(track.conf, det.conf)
        track.hits += 1
        track.last_seen = now
        if not track.typed and track.hits >= 2:
            return track
        if track.typed and track.retries < self.max_retries and now - track.typed_at >= self.retry_delay:
            return track
        return None

    def mark_typed(self, track: Track, now: float | None = None) -> None:
        now = time.perf_counter() if now is None else now
        if track.typed:
            track.retries += 1
        track.typed = True
        track.typed_at = now
        track.last_seen = now

    def _match_place(self, det: Det) -> Track | None:
        best: Track | None = None
        best_dist = 1e9
        for track in self.tracks:
            if track.text == det.text:
                continue
            dx = abs(track.cx - det.cx)
            dy = abs(track.cy - det.cy)
            if dx > max(track.w, det.w, 40) * 0.55:
                continue
            if dy > max(70.0, track.h, det.h) + 36:
                continue
            dist = dx + dy
            if dist < best_dist:
                best = track
                best_dist = dist
        return best

    def _match(self, det: Det) -> Track | None:
        best: Track | None = None
        best_dist = self.radius
        for track in self.tracks:
            if track.text != det.text:
                continue
            dist = math.hypot(track.cx - det.cx, track.cy - det.cy)
            if dist < best_dist:
                best = track
                best_dist = dist
        return best
