"""Turn OCR pieces into the exact string the mini-game wants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz.distance import Levenshtein

LEXICON_PATH = Path(__file__).with_name("lexicon.txt")

_PUNCT_TRANSLATION = str.maketrans({
    "\u2019": "",
    "\u2018": "",
    "`": "",
    "\u00b4": "",
})
_OCR_TRANSLATION = str.maketrans({"0": "o", "1": "l", "5": "s", "8": "b", "|": "l"})

# HUD and client chrome. Hero and item names are intentionally not listed.
BLOCKLIST = {
    "score",
    "time",
    "high",
    "highscore",
    "tickets",
    "ticket",
    "progress",
    "chapter",
    "minigame",
    "minigames",
    "play",
    "playdota",
    "dota",
    "activate",
    "windows",
    "settings",
    "gotosettings",
    "midnight",
    "midnightrun",
    "carnival",
    "darkcarnival",
    "trade",
    "daily",
    "available",
    "secret",
    "secretroom",
    "pause",
    "paused",
    "lobby",
    "nerd",
    "close",
}


@dataclass
class Piece:
    raw: str
    conf: float
    x: int
    y: int
    w: int
    h: int

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class Det:
    text: str
    conf: float
    x: int
    y: int
    w: int
    h: int
    lexicon: bool
    raw: str

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


def normalize(text: str) -> str:
    """Letters and digits only. Spaces and punctuation are not typed."""
    text = text.lower().translate(_PUNCT_TRANSLATION)
    text = text.replace("'", "")
    return re.sub(r"[^a-z0-9]", "", text)


def _strip_trailing_score(text: str) -> str:
    return re.sub(r"[\s:,\-]*\d{1,4}$", "", text).strip()


def _collapse_stacked_copy(text: str) -> str:
    parts = text.split()
    if len(parts) == 2 and parts[0].lower() == parts[1].lower():
        return parts[0]
    compact = normalize(text)
    if len(compact) >= 4 and len(compact) % 2 == 0:
        half = len(compact) // 2
        if compact[:half] == compact[half:]:
            return compact[:half]
    return text


def _has_vowel(text: str) -> bool:
    return any(ch in "aeiou" for ch in text)


def _is_numeric_token(text: str) -> bool:
    return bool(re.fullmatch(r"x?\d+", text))


class Lexicon:
    def __init__(self, words: set[str]) -> None:
        self.words = words
        self._keys = list(words)

    @classmethod
    def load(cls, path: Path | None = None) -> "Lexicon":
        path = path or LEXICON_PATH
        words: set[str] = set()
        if path.exists():
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.split("#", 1)[0].strip()
                if not line:
                    continue
                norm = normalize(line)
                if len(norm) >= 2:
                    words.add(norm)
        return cls(words)

    def correct(self, norm: str) -> str | None:
        if norm in self.words:
            return norm
        folded = norm.translate(_OCR_TRANSLATION)
        if folded in self.words:
            return folded
        if len(folded) < 4 or not self._keys:
            return None
        # One edit under 8 letters, two edits after that. Ties are rejected so
        # Lina is never rewritten as Lion.
        limit = 1 if len(folded) < 8 else 2
        ranked = sorted(
            (
                word
                for word in self._keys
                if abs(len(word) - len(folded)) <= limit
            ),
            key=lambda word: Levenshtein.distance(folded, word),
        )
        if not ranked:
            return None
        best_dist = Levenshtein.distance(folded, ranked[0])
        if best_dist > limit:
            return None
        if len(ranked) > 1 and Levenshtein.distance(folded, ranked[1]) == best_dist:
            return None
        return ranked[0]


def decide(raw: str, conf: float, lexicon: Lexicon, raw_confidence: float) -> tuple[str, bool] | None:
    cleaned = _collapse_stacked_copy(_strip_trailing_score(raw))
    norm = normalize(cleaned)
    if not norm or norm in BLOCKLIST or _is_numeric_token(norm):
        return None
    if len(norm) > 48:
        return None

    suggestion = lexicon.correct(norm)
    if suggestion is None:
        prefix = re.fullmatch(r"([a-z]{3,})(\d{1,4})", norm)
        if prefix:
            suggestion = lexicon.correct(prefix.group(1))
    if suggestion is not None:
        if len(suggestion) <= 2 and conf < 0.75:
            return None
        return suggestion, True

    if (
        conf >= raw_confidence
        and len(norm) >= 4
        and re.fullmatch(r"[a-z]+", norm)
        and _has_vowel(norm)
        and norm not in BLOCKLIST
    ):
        return norm, False
    return None


def group_phrases(pieces: list[Piece]) -> list[Piece]:
    """Join letters that belong to one falling label. Keep separate labels apart."""
    usable = []
    for piece in pieces:
        token = normalize(_strip_trailing_score(piece.raw))
        if not token or _is_numeric_token(token):
            continue
        usable.append(piece)
    if not usable:
        return []

    usable.sort(key=lambda p: (p.cy, p.x))
    lines: list[list[Piece]] = []
    for piece in usable:
        if not lines:
            lines.append([piece])
            continue
        line = lines[-1]
        anchor = line[0]
        tolerance = max(piece.h, anchor.h, 8) * 0.6
        mean_y = sum(p.cy for p in line) / len(line)
        if abs(piece.cy - mean_y) <= tolerance:
            line.append(piece)
        else:
            lines.append([piece])

    phrases: list[Piece] = []
    for line in lines:
        line.sort(key=lambda p: p.x)
        current = [line[0]]
        for nxt in line[1:]:
            prev = current[-1]
            gap = nxt.x - (prev.x + prev.w)
            char_w = max(6.0, prev.w / max(len(prev.raw.strip()), 1))
            if gap <= max(14.0, char_w * 1.8):
                current.append(nxt)
            else:
                phrases.append(_join(current))
                current = [nxt]
        phrases.append(_join(current))
    return phrases


def _join(parts: list[Piece]) -> Piece:
    raw = " ".join(p.raw.strip() for p in parts)
    x = min(p.x for p in parts)
    y = min(p.y for p in parts)
    right = max(p.x + p.w for p in parts)
    bottom = max(p.y + p.h for p in parts)
    conf = min(p.conf for p in parts)
    return Piece(raw=raw, conf=conf, x=x, y=y, w=right - x, h=bottom - y)


def to_detections(
    phrases: list[Piece],
    lexicon: Lexicon,
    min_confidence: float,
    raw_confidence: float,
) -> list[Det]:
    found: list[Det] = []
    for phrase in phrases:
        if phrase.conf < min_confidence:
            continue
        decided = decide(phrase.raw, phrase.conf, lexicon, raw_confidence)
        if decided is None:
            continue
        text, from_lexicon = decided
        found.append(
            Det(
                text=text,
                conf=phrase.conf,
                x=phrase.x,
                y=phrase.y,
                w=phrase.w,
                h=phrase.h,
                lexicon=from_lexicon,
                raw=phrase.raw,
            )
        )
    return _dedup(found)


def _dedup(dets: list[Det]) -> list[Det]:
    kept: list[Det] = []
    for det in sorted(dets, key=lambda d: d.conf, reverse=True):
        duplicate = False
        for other in kept:
            if det.text != other.text:
                continue
            x_close = abs(det.cx - other.cx) < max(det.w, other.w, 20) * 0.75
            y_close = abs(det.cy - other.cy) < max(det.h, other.h, 12) * 1.4
            if x_close and y_close:
                duplicate = True
                break
        if not duplicate:
            kept.append(det)
    return kept


def split_by_danger(dets: list[Det], height: int, danger_y_ratio: float) -> tuple[list[Det], list[Det]]:
    cutoff = height * danger_y_ratio
    danger = [d for d in dets if d.cy >= cutoff]
    safe = [d for d in dets if d.cy < cutoff]
    danger.sort(key=lambda d: -d.cy)
    # Short labels first while they are still safe, so the multiplier is higher
    # by the time a long label is cleared.
    safe.sort(key=lambda d: (len(d.text), -d.cy))
    return danger, safe
