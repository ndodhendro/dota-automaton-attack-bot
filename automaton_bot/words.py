"""Turn OCR pieces into the exact string the mini-game wants."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from rapidfuzz.distance import Levenshtein

LEXICON_PATH = Path(__file__).with_name("lexicon.txt")
LEARNED_PATH = Path(__file__).with_name("learned.txt")

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
    def __init__(self, words: set[str], learned_path: Path | None = None) -> None:
        self.words = words
        self._keys = list(words)
        self.learned_path = learned_path

    @classmethod
    def load(cls, path: Path | None = None, learned_path: Path | None = None) -> "Lexicon":
        path = path or LEXICON_PATH
        learned_path = LEARNED_PATH if learned_path is None else learned_path
        words = _read_word_file(path)
        words.update(_read_word_file(learned_path))
        return cls(words, learned_path)

    def remember(self, text: str, conf: float) -> str | None:
        """Store a clean high-confidence read so a later near-miss can snap to it."""
        if conf < 0.99:
            return None
        norm = normalize(text)
        if norm in self.words or norm in BLOCKLIST or _is_numeric_token(norm):
            return None
        if not (4 <= len(norm) <= 80) or not re.fullmatch(r"[a-z]+", norm) or not _has_vowel(norm):
            return None
        self.words.add(norm)
        self._keys.append(norm)
        if self.learned_path is not None:
            with self.learned_path.open("a", encoding="utf-8") as handle:
                handle.write(norm + "\n")
        return norm

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

    def complete(self, norm: str) -> str | None:
        """Expand one wrapped line to the only longer phrase that contains it."""
        folded = norm.translate(_OCR_TRANSLATION)
        if len(folded) < 8 or folded in self.words:
            return None
        found: str | None = None
        seen: set[str] = set()
        for word in self._keys:
            if word in seen or len(word) < len(folded) + 4:
                continue
            seen.add(word)
            if folded not in word:
                continue
            if found is not None:
                return None
            found = word
        return found


def _read_word_file(path: Path) -> set[str]:
    words: set[str] = set()
    if not path.exists():
        return words
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.split("#", 1)[0].strip()
        if not line:
            continue
        norm = normalize(line)
        if len(norm) >= 2:
            words.add(norm)
    return words


def _is_hud(norm: str) -> bool:
    if norm in BLOCKLIST:
        return True
    if len(norm) < 4:
        return False
    for word in BLOCKLIST:
        if abs(len(word) - len(norm)) > 1:
            continue
        if Levenshtein.distance(norm, word) <= 1:
            return True
    return False


def _short_name(norm: str, lexicon: Lexicon) -> str | None:
    """Keep Io, Kez, and Riki when OCR turns i/l/1 or o/0 into each other."""
    if not (2 <= len(norm) <= 4):
        return None
    folds = (
        norm,
        norm.translate(_OCR_TRANSLATION),
        norm.translate(str.maketrans({"0": "o", "1": "i", "5": "s", "8": "b", "|": "i", "2": "z"})),
        norm.translate(str.maketrans({"0": "o", "1": "i", "l": "i", "5": "s", "2": "z", "|": "i"})),
    )
    hits = {item for item in folds if item in lexicon.words}
    if len(hits) == 1:
        return next(iter(hits))
    return None


def remainder_of(raw: str, full: str, highlight: str) -> str | None:
    """Letters the game still wants after a known phrase was partly accepted.

    A whole highlighted word such as FROM still means the sentence has not
    started. LLECTION is only the tail of COLLECTION, so that tail is enough.
    """
    frag = normalize(highlight)
    if len(frag) < 4 or not full.endswith(frag) or frag == full:
        return None
    words = [normalize(part) for part in re.split(r"[^a-zA-Z0-9]+", raw) if part.strip()]
    if any(word == frag for word in words):
        return None
    if any(len(word) > len(frag) and word.endswith(frag) for word in words):
        return frag
    return None


def decide(raw: str, conf: float, lexicon: Lexicon, raw_confidence: float) -> tuple[str, bool] | None:
    # Check the raw token first so a trailing digit inside Ke2 or Io's "10"
    # is not thrown away as a point value.
    raw_norm = normalize(raw)
    short = _short_name(raw_norm, lexicon)
    cleaned = _collapse_stacked_copy(_strip_trailing_score(raw))
    norm = normalize(cleaned)
    if short is None and norm:
        short = _short_name(norm, lexicon)
    if short is not None:
        if len(short) <= 2 and conf < 0.45:
            return None
        return short, True
    if _is_hud(norm) or _is_numeric_token(norm):
        return None
    if len(norm) > 80:
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

    completed = lexicon.complete(norm)
    if completed is not None:
        return completed, True

    if (
        conf >= raw_confidence
        and len(norm) >= 4
        and re.fullmatch(r"[a-z]+", norm)
        and _has_vowel(norm)
        and not _is_hud(norm)
    ):
        return norm, False
    return None


def group_phrases(pieces: list[Piece]) -> list[Piece]:
    """Join letters that belong to one falling label. Keep separate labels apart."""
    usable = []
    for piece in pieces:
        token = normalize(_strip_trailing_score(piece.raw))
        bare = normalize(piece.raw)
        if not token and not (2 <= len(bare) <= 4):
            continue
        if token and _is_numeric_token(token):
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
    return _stack_lines(phrases)


def _stack_lines(phrases: list[Piece]) -> list[Piece]:
    """Join the 2-3 wrapped lines of one falling label, top to bottom.

    A short bright line such as FROM is the same label as the small sentence
    above it. A label sitting somewhere else on the board stays separate.
    """
    if len(phrases) < 2:
        return phrases
    phrases = sorted(phrases, key=lambda phrase: phrase.cy)
    used = [False] * len(phrases)
    stacked: list[Piece] = []
    for index, phrase in enumerate(phrases):
        if used[index]:
            continue
        group = [phrase]
        used[index] = True
        grew = True
        while grew:
            grew = False
            cover = _join(group)
            for other_index, other in enumerate(phrases):
                if used[other_index] or not _same_label(cover, other):
                    continue
                group.append(other)
                used[other_index] = True
                grew = True
        stacked.append(_collapse_wrapped(group))
    return stacked


def _same_label(cover: Piece, other: Piece) -> bool:
    overlap = min(cover.x + cover.w, other.x + other.w) - max(cover.x, other.x)
    narrower = min(cover.w, other.w)
    centers = abs(cover.cx - other.cx)
    aligned = narrower > 0 and (overlap >= narrower * 0.45 or centers <= max(cover.w, other.w) * 0.35)
    if not aligned:
        return False
    if other.y >= cover.y + cover.h:
        gap = other.y - (cover.y + cover.h)
    elif cover.y >= other.y + other.h:
        gap = cover.y - (other.y + other.h)
    else:
        gap = 0
    return gap <= max(96, max(cover.h, other.h) * 3.2)


def _collapse_wrapped(group: list[Piece]) -> Piece:
    ordered = sorted(group, key=lambda phrase: phrase.y)
    if len(ordered) == 1:
        return ordered[0]
    ranked = sorted(
        ((phrase, normalize(_strip_trailing_score(phrase.raw))) for phrase in ordered),
        key=lambda item: len(item[1]),
        reverse=True,
    )
    longest_piece, longest = ranked[0]
    fragments_fit = all(len(text) < 4 or text in longest for _, text in ranked[1:])
    cover = _join(ordered)
    if longest and fragments_fit:
        return Piece(
            raw=longest_piece.raw,
            conf=max(phrase.conf for phrase in ordered),
            x=cover.x,
            y=cover.y,
            w=cover.w,
            h=cover.h,
        )
    return cover


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
