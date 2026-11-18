"""The Qur'an text, and the normalisation that lets speech-recognised Arabic be
compared with it.

Two Tanzil texts ship in ``data/``: *simple-clean* (no diacritics), which the
matcher searches, and *Uthmani*, which is what a matched quotation is replaced
with. Both are used verbatim under Tanzil's terms (see the notice at the end of
each file): the text may not be changed, and its source must be credited.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from importlib import resources

# Diacritics (harakat, tanwin, shadda, sukun), Qur'anic annotation marks, the
# superscript alef and tatweel: none of them survive speech recognition reliably,
# so none of them take part in matching.
_MARKS = re.compile("[ؐ-ًؚ-ٰٟۖ-ۭـ]")
_FOLD = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا", "ٱ": "ا",  # أ إ آ ٱ -> ا
    "ى": "ي",  # ى -> ي
    "ة": "ه",  # ة -> ه
    "ؤ": "و",  # ؤ -> و
    "ئ": "ي",  # ئ -> ي
    "ء": None,      # a lone hamza is dropped
})
_NOT_ARABIC_LETTER = re.compile("[^ء-ي]")


def normalize_word(word: str) -> str:
    """One word, reduced to the letters speech recognition gets right most often.

    Returns "" for anything with no Arabic letters (English words, numbers,
    punctuation), which the matcher treats as a gap.
    """
    w = unicodedata.normalize("NFC", word)
    w = _MARKS.sub("", w).translate(_FOLD)
    return _NOT_ARABIC_LETTER.sub("", w)


def tokenize(text: str) -> list[str]:
    """Whitespace tokens, as written. Normalise each with normalize_word."""
    return text.split()


@dataclass(frozen=True)
class Ayah:
    sura: int
    aya: int
    simple: str
    uthmani: str
    # True when the mushaf prints the basmala above this ayah. Tanzil's files carry
    # it inside the first ayah of 112 surahs; it is held apart here, because it is
    # an ayah in its own right only in al-Fatihah (1:1) and an-Naml (27:30).
    basmala: bool = False

    @property
    def ref(self) -> str:
        return f"{self.sura}:{self.aya}"


@dataclass(frozen=True)
class Word:
    """One word of the simple text, with where it sits."""
    sura: int
    aya: int
    index: int  # position within the ayah, from 0
    norm: str


class Quran:
    """The whole text, as ayat and as one flat run of words for matching."""

    def __init__(self, ayat: list[Ayah]):
        self.ayat = ayat
        self.by_ref = {(a.sura, a.aya): a for a in ayat}
        self.words: list[Word] = []
        for a in ayat:
            for i, w in enumerate(tokenize(a.simple)):
                self.words.append(Word(a.sura, a.aya, i, normalize_word(w)))

    def ayah(self, sura: int, aya: int) -> Ayah:
        return self.by_ref[(sura, aya)]


def _read(name: str) -> dict[tuple[int, int], str]:
    out = {}
    text = resources.files("khutbah").joinpath("data", name).read_text(encoding="utf-8")
    for line in text.splitlines():
        if not line or line.startswith("#"):
            continue
        sura, aya, body = line.split("|", 2)
        out[(int(sura), int(aya))] = body
    return out


BASMALA = ["بسم", "الله", "الرحمن", "الرحيم"]


def _split_basmala(sura: int, aya: int, simple: str, uthmani: str) -> Ayah:
    """Separate the printed basmala from the first ayah of a surah (not 1 or 9).

    The text files are left exactly as Tanzil publishes them; this only changes
    how the words are held in memory.
    """
    if aya == 1 and sura not in (1, 9):
        sw, uw = simple.split(), uthmani.split()
        if [normalize_word(w) for w in sw[:4]] == BASMALA and [normalize_word(w) for w in uw[:4]] == BASMALA:
            return Ayah(sura, aya, " ".join(sw[4:]), " ".join(uw[4:]), basmala=True)
    return Ayah(sura, aya, simple, uthmani)


@lru_cache(maxsize=1)
def load() -> Quran:
    """The Qur'an, loaded once per process."""
    simple = _read("quran-simple-clean.txt")
    uthmani = _read("quran-uthmani.txt")
    if len(simple) != 6236 or simple.keys() != uthmani.keys():
        raise RuntimeError("the bundled Qur'an texts are incomplete or do not line up")
    ayat = [_split_basmala(s, a, simple[(s, a)], uthmani[(s, a)]) for (s, a) in sorted(simple)]
    if sum(a.basmala for a in ayat) != 112:
        raise RuntimeError("expected the printed basmala on 112 surahs")
    return Quran(ayat)
