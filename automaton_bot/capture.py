"""Grab the mini-game region from the primary monitor."""

from __future__ import annotations

import numpy as np


class Screen:
    def __init__(self) -> None:
        import mss

        self._mss = mss.mss()
        self.monitor = self._mss.monitors[1]

    def grab(self, region: dict) -> np.ndarray:
        shot = self._mss.grab(region)
        # mss is BGRA. Drop alpha; OpenCV expects BGR.
        return np.asarray(shot)[:, :, :3].copy()

    def grab_monitor(self) -> np.ndarray:
        return self.grab(self.monitor)

    def close(self) -> None:
        self._mss.close()
