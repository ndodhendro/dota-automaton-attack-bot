"""Load and save the bot config next to the project root."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "config.json"

# Modal rectangle measured from a 1920x1080 Dark Carnival screenshot.
# Fractions of the primary monitor. Override with F9 calibration.
DEFAULT_REGION_FRACTION = (0.2461, 0.0487, 0.7578, 0.9496)

DEFAULTS = {
    "region": None,
    "key_hold_ms": 6,
    "key_interval_ms": 8,
    "inter_word_ms": 20,
    "danger_y_ratio": 0.58,
    "hud_top_ratio": 0.09,
    "min_confidence": 0.40,
    "raw_confidence": 0.80,
    "retry_delay_ms": 200,
    "retries": 1,
    "match_radius": 170,
}


def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_PATH.exists():
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            cfg.update(data)
    return cfg


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def default_region(monitor: dict) -> dict:
    x1, y1, x2, y2 = DEFAULT_REGION_FRACTION
    width = int(monitor["width"])
    height = int(monitor["height"])
    left = int(monitor["left"] + x1 * width)
    top = int(monitor["top"] + y1 * height)
    return {
        "left": left,
        "top": top,
        "width": max(1, int((x2 - x1) * width)),
        "height": max(1, int((y2 - y1) * height)),
    }


def active_region(cfg: dict, monitor: dict) -> dict:
    region = cfg.get("region")
    if isinstance(region, dict) and {"left", "top", "width", "height"} <= set(region):
        return {
            "left": int(region["left"]),
            "top": int(region["top"]),
            "width": int(region["width"]),
            "height": int(region["height"]),
        }
    return default_region(monitor)
