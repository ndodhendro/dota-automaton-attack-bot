"""Remember words that were already typed so falling labels are not repeated."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from automaton_bot.words import Det


def _contains(longer: str, shorter: str) -> bool:
    return len(shorter) >= 4 and shorter in longer


def _related(a: str, b: str) -> bool:
    """True when the new read is the same label with overlapping ink, not the next one."""
    if _contains(a, b) or _contains(b, a):
        return True
    shared = 0
    for left, right in zip(a, b):
        if left != right:
            break
        shared += 1
    return shared >= 8


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
    pending: str = ""


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
            if occupied is not None and _related(occupied.text, det.text):
                # Overlapping ink of the label already in hand. A different
                # phrase that spawned here is not related and is typed below.
                if (
                    not occupied.typed
                    and len(det.text) > len(occupied.text)
                    and det.conf >= occupied.conf
                    and _contains(det.text, occupied.text)
                ):
                    occupied.text = det.text
                    occupied.conf = det.conf
                    self._touch(occupied, det, now)
                    return occupied
                if occupied.typed and det.text.startswith(occupied.text) and len(det.text) > len(occupied.text):
                    occupied.pending = det.text[len(occupied.text) :]
                    occupied.text = det.text
                    occupied.conf = max(occupied.conf, det.conf)
                    occupied.last_seen = now
                    return occupied
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
            return track
        self._touch(track, det, now)
        if not track.typed:
            return track
        if track.retries < self.max_retries and now - track.typed_at >= self.retry_delay:
            return track
        return None

    def _touch(self, track: Track, det: Det, now: float) -> None:
        track.cx = det.cx
        track.cy = det.cy
        track.w = det.w
        track.h = det.h
        track.conf = max(track.conf, det.conf)
        track.hits += 1
        track.last_seen = now

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
