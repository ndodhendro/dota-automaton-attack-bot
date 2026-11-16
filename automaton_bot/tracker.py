"""Remember words that were already typed so falling labels are not repeated."""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from automaton_bot.words import Det


@dataclass
class Track:
    text: str
    cx: float
    cy: float
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
            track = Track(text=det.text, cx=det.cx, cy=det.cy, last_seen=now)
            self.tracks.append(track)
            return track
        track.cx = det.cx
        track.cy = det.cy
        track.last_seen = now
        if not track.typed:
            return track
        if track.retries < self.max_retries and now - track.typed_at >= self.retry_delay:
            return track
        return None

    def mark_typed(self, track: Track, now: float | None = None) -> None:
        now = time.perf_counter() if now is None else now
        if track.typed:
            track.retries += 1
        track.typed = True
        track.typed_at = now
        track.last_seen = now

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
