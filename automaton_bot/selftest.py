"""Offline checks for parsing, grouping, and de-duplication."""

from __future__ import annotations

from pathlib import Path
import tempfile

from automaton_bot.tracker import Tracker
from automaton_bot.words import (
    Det,
    Lexicon,
    Piece,
    decide,
    group_phrases,
    remainder_of,
    stuck_tail,
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
        "kez",
        "riki",
        "naturesprophet",
    })

    _check(normalize("Anti-Mage") == "antimage", "hyphen")
    _check(normalize("Nature's Prophet") == "naturesprophet", "apostrophe")
    _check(normalize("Ring of Protection") == "ringofprotection", "spaces")

    text, used = decide("KAYA 10", 0.9, lexicon, 0.8)
    _check(text == "kaya" and used, "trailing score")
    _check(decide("SCORE", 0.99, lexicon, 0.8) is None, "hud")
    _check(decide("TIMAE", 0.9, lexicon, 0.8) is None, "misread time stays out")
    _check(decide("IO", 0.55, lexicon, 0.8) == ("io", True), "short io")
    _check(decide("10", 0.8, lexicon, 0.8) == ("io", True), "io read as digits")
    _check(decide("KE2", 0.7, lexicon, 0.8) == ("kez", True), "kez with a digit")
    _check(decide("R1K1", 0.7, lexicon, 0.8) == ("riki", True), "riki with thin i")
    _check(decide("IO", 0.3, lexicon, 0.8) is None, "very weak io is dropped")
    phrase = "A BEAUTIFUL SOUL FOR MY COLLECTION."
    full = "abeautifulsoulformycollection"
    _check(remainder_of(phrase, full, "FROM") is None, "a whole highlighted word stays with the sentence")
    _check(remainder_of(phrase, full, "COLLECTION") is None, "the whole last word is not a tail")
    _check(remainder_of(phrase, full, "LLECTION") == "llection", "mid-word highlight is the missing tail")
    hunter = Lexicon({"tidehunter"})
    _check(decide("tideunter", 0.9, hunter, 0.8) == ("tidehunter", True), "missing h is corrected")
    _check(stuck_tail("tideunter", "tidehunter") == "hunter", "typo continues at the missing letter")
    _check(stuck_tail("tidehunter", "tidehunter") is None, "exact send needs no tail")
    _check(remainder_of("TIDEHUNTER", "tidehunter", "HUNTER") == "hunter", "highlight shows the untyped tail")
    _check(decide("x2.0", 0.99, lexicon, 0.8) is None, "multiplier")
    _check(decide("0:30", 0.99, lexicon, 0.8) is None, "timer")
    _check(decide("antlmage", 0.7, lexicon, 0.8)[0] == "antimage", "one edit")
    _check(decide("lina", 0.7, lexicon, 0.8)[0] == "lina", "lina stays lina")
    _check(decide("lion", 0.95, lexicon, 0.8) == ("lion", False), "lion is not rewritten")
    _check(decide("lion", 0.4, lexicon, 0.8) is None, "weak unknown is dropped")
    _check(decide("starstorm", 0.9, lexicon, 0.8) == ("starstorm", False), "raw fallback")
    with tempfile.TemporaryDirectory() as folder:
        learned = Path(folder) / "learned.txt"
        fresh = Lexicon(set(lexicon.words), learned)
        _check(fresh.remember("kaya", 1.0) is None, "known word is not stored again")
        _check(fresh.remember("stormwascoming", 0.98) is None, "below 99 percent stays out")
        stored = fresh.remember("toldyouastormwascoming", 0.995)
        _check(stored == "toldyouastormwascoming", "clean 99 percent read is stored")
        again = Lexicon.load(Path(folder) / "missing.txt", learned)
        _check(again.correct("toldyouastormwascomlng") == "toldyouastormwascoming", "later near-miss uses the stored phrase")
        _check(
            decide("WAS COMING!", 0.91, fresh, 0.8) == ("toldyouastormwascoming", True),
            "lower line types the whole phrase",
        )
        _check(
            decide("TOLD YOU A STORM", 0.91, fresh, 0.8) == ("toldyouastormwascoming", True),
            "upper line types the whole phrase",
        )
        _check(decide("luna", 0.9, fresh, 0.8)[0] == "luna", "exact short label stays")
        _check(decide("storm", 0.95, fresh, 0.8) == ("storm", False), "a short slice stays as read")
        fresh.remember("iknewastormwascoming", 1.0)
        _check(decide("STORM WAS COMING", 0.95, fresh, 0.8) == ("stormwascoming", False), "shared slice is not guessed")

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

    wrapped = to_detections(
        group_phrases([
            Piece("WE HAVE MORE WHERE THAT CAME FROM.", 0.99, 276, 553, 294, 12),
            Piece("FROM", 0.99, 370, 648, 109, 28),
            Piece("DEMON EATER", 0.92, 80, 700, 180, 28),
            Piece("TOLD YOU A STORM", 0.96, 500, 140, 280, 30),
            Piece("WAS COMING!", 0.99, 540, 190, 220, 30),
        ]),
        lexicon,
        0.4,
        0.8,
    )
    wrapped_text = sorted(det.text for det in wrapped)
    _check(
        wrapped_text == ["demoneater", "toldyouastormwascoming", "wehavemorewherethatcamefrom"],
        f"wrapped lines {wrapped_text}",
    )

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
    _check(first is not None, "first clean look is typed immediately")
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
    other = tracker.observe(Det("kaya", 0.9, 400, 260, 60, 20, True, "kaya"), now=1.82)
    _check(other is not None and other is not first, "a second kaya elsewhere is new")
    spawned = tracker.observe(Det("luna", 0.95, 48, 250, 60, 20, True, "luna"), now=1.9)
    _check(spawned is not None and spawned.text == "luna", "the next label in the same place is typed")

    phrase = Det("wehavemorewherethatcamefrom", 0.99, 200, 100, 300, 14, False, "full")
    locked = tracker.observe(phrase, now=3.0)
    _check(locked is not None, "sentence is typed on the first look")
    tracker.mark_typed(locked, now=3.0)
    mixed = Det("wehavemoredemonedge", 0.91, 210, 112, 320, 18, False, "mixed")
    _check(tracker.observe(mixed, now=3.1) is None, "overlapping read is ignored")

    partial = Det("abeautifulsoulformyco", 0.9, 120, 400, 180, 12, False, "A BEAUTIFUL SOUL FOR MY CO")
    started = tracker.observe(partial, now=4.0)
    tracker.mark_typed(started, now=4.0)
    rest = tracker.observe(
        Det("abeautifulsoulformycollection", 0.97, 120, 402, 289, 11, True, "A BEAUTIFUL SOUL FOR MY COLLECTION."),
        now=4.1,
    )
    _check(rest is started and rest.pending == "llection", "the stored phrase finishes the typed prefix")

    fresh_tracker = Tracker(radius=170, retry_delay=0.2, max_retries=1)
    typo = Det("tideunter", 0.9, 30, 300, 80, 16, False, "tideunter")
    typed_typo = fresh_tracker.observe(typo, now=5.0)
    fresh_tracker.mark_typed(typed_typo, now=5.0)
    typed_typo.sent = "tideunter"
    repaired = fresh_tracker.observe(Det("tidehunter", 0.95, 32, 304, 90, 16, True, "tidehunter"), now=5.05)
    _check(repaired is typed_typo and repaired.pending == "hunter", "a stuck typo is finished, not retyped")

    print("self-test ok")
