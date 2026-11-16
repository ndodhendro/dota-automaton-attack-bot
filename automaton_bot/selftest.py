"""Offline checks for parsing, grouping, and de-duplication."""

from __future__ import annotations

from automaton_bot.tracker import Tracker
from automaton_bot.words import (
    Det,
    Lexicon,
    Piece,
    decide,
    group_phrases,
    normalize,
    split_by_danger,
    to_detections,
)


def _check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def run() -> None:
    lexicon = Lexicon({
        "antimage",
        "luna",
        "lina",
        "kaya",
        "ringofprotection",
        "blackkingbar",
        "io",
        "naturesprophet",
    })

    _check(normalize("Anti-Mage") == "antimage", "hyphen")
    _check(normalize("Nature's Prophet") == "naturesprophet", "apostrophe")
    _check(normalize("Ring of Protection") == "ringofprotection", "spaces")

    text, used = decide("KAYA 10", 0.9, lexicon, 0.8)
    _check(text == "kaya" and used, "trailing score")
    _check(decide("SCORE", 0.99, lexicon, 0.8) is None, "hud")
    _check(decide("x2.0", 0.99, lexicon, 0.8) is None, "multiplier")
    _check(decide("0:30", 0.99, lexicon, 0.8) is None, "timer")
    _check(decide("antlmage", 0.7, lexicon, 0.8)[0] == "antimage", "one edit")
    _check(decide("lina", 0.7, lexicon, 0.8)[0] == "lina", "lina stays lina")
    _check(decide("lion", 0.95, lexicon, 0.8) == ("lion", False), "lion is not rewritten")
    _check(decide("lion", 0.4, lexicon, 0.8) is None, "weak unknown is dropped")
    _check(decide("starstorm", 0.9, lexicon, 0.8) == ("starstorm", False), "raw fallback")

    pieces = [
        Piece("Ring", 0.95, 10, 40, 40, 18),
        Piece("of", 0.95, 56, 40, 18, 18),
        Piece("Protection", 0.91, 80, 42, 120, 18),
        Piece("10", 0.9, 18, 64, 16, 12),
        Piece("Rubick", 0.88, 360, 40, 70, 18),
        Piece("KAYA", 0.93, 30, 200, 60, 20),
        Piece("KAYA", 0.9, 32, 214, 60, 20),
    ]
    dets = to_detections(group_phrases(pieces), lexicon, 0.4, 0.8)
    typed = sorted(det.text for det in dets)
    _check(typed == ["kaya", "ringofprotection", "rubick"], f"grouped {typed}")
    kaya = next(det for det in dets if det.text == "kaya")
    _check(kaya.y == 200, "dedup kept the stronger kaya")

    danger, safe = split_by_danger(
        [
            Det("kaya", 0.9, 0, 10, 40, 16, True, "kaya"),
            Det("blackkingbar", 0.9, 0, 80, 80, 16, True, "bkb"),
            Det("luna", 0.9, 0, 400, 40, 16, True, "luna"),
        ],
        height=500,
        danger_y_ratio=0.58,
    )
    _check([d.text for d in danger] == ["luna"], "lowest label is cleared first")
    _check([d.text for d in safe] == ["kaya", "blackkingbar"], "safe short label first")

    tracker = Tracker(radius=170, retry_delay=0.2, max_retries=1)
    first = tracker.observe(kaya, now=1.0)
    _check(first is not None, "first sight")
    again = tracker.observe(Det("kaya", 0.9, 40, 220, 60, 20, True, "kaya"), now=1.1)
    _check(again is first, "same falling label")
    tracker.mark_typed(first, now=1.1)
    held = tracker.observe(Det("kaya", 0.9, 48, 240, 60, 20, True, "kaya"), now=1.2)
    _check(held is None, "no immediate repeat")
    retry = tracker.observe(Det("kaya", 0.9, 52, 250, 60, 20, True, "kaya"), now=1.4)
    _check(retry is first, "one retry if it is still there")
    tracker.mark_typed(retry, now=1.4)
    done = tracker.observe(Det("kaya", 0.9, 56, 260, 60, 20, True, "kaya"), now=1.8)
    _check(done is None, "retry only once")
    other = tracker.observe(Det("kaya", 0.9, 400, 260, 60, 20, True, "kaya"), now=1.8)
    _check(other is not None and other is not first, "a second kaya elsewhere is new")

    print("self-test ok")
