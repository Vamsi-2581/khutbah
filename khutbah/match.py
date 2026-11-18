"""Finding Qur'an quotations in a transcript.

Speech recognition garbles exactly the Arabic that matters in an English khutbah:
words dropped, merged, misheard, diacritics lost. So matching is not string
search. It is:

1. **Seed.** Every run of three consecutive transcript words that also occurs in
   the Qur'an marks a candidate position.
2. **Align.** Around each candidate, the transcript and the Qur'an are aligned
   word by word (local alignment, Smith-Waterman style) with a similarity that
   forgives small spelling differences, so a misheard word costs a little rather
   than ending the match.
3. **Decide.** A candidate becomes a quotation only if enough Qur'an words were
   matched and the alignment is good enough. Overlapping candidates keep the best.
4. **Be honest about ambiguity.** Many phrases occur more than once (the basmala
   opens the Fatihah and appears in an-Naml; a refrain repeats 31 times in
   ar-Rahman). When several places fit equally well they are all reported, and
   the quotation is marked ambiguous rather than guessed.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from .quran import Quran, load, normalize_word, tokenize

SEED = 3


@dataclass(frozen=True)
class Place:
    """A run of Qur'an words: from (sura, aya, word) to (sura, aya, word), inclusive."""
    start: tuple[int, int, int]
    end: tuple[int, int, int]

    @property
    def ref(self) -> str:
        (s1, a1, _), (s2, a2, _) = self.start, self.end
        if (s1, a1) == (s2, a2):
            return f"{s1}:{a1}"
        if s1 == s2:
            return f"{s1}:{a1}-{a2}"
        return f"{s1}:{a1}-{s2}:{a2}"


@dataclass
class Quotation:
    """A span of the transcript (token indices, end exclusive) that quotes the Qur'an."""
    start: int
    end: int
    place: Place
    confidence: float
    matched_words: int
    alternatives: list[Place] = field(default_factory=list)
    partial: bool = False

    @property
    def ambiguous(self) -> bool:
        return bool(self.alternatives)

    @property
    def ref(self) -> str:
        return self.place.ref


def _edit_distance(a: str, b: str) -> int:
    if a == b:
        return 0
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


# The definite article and the particles that attach to it. Shared by most nouns,
# they make unrelated words look alike (الصابرين / الكافرين), so near-matches are
# judged on what follows them.
_ARTICLE = ("وال", "فال", "بال", "كال", "لل", "ال")


def _stem(w: str) -> str:
    for p in _ARTICLE:
        if w.startswith(p) and len(w) - len(p) >= 2:
            return w[len(p):]
    return w


def similarity(a: str, b: str) -> float:
    """1.0 for the same word, down to 0.0; forgiving of one wrong letter in the stem."""
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    sa, sb = _stem(a), _stem(b)
    return max(0.0, 1.0 - _edit_distance(sa, sb) / max(len(sa), len(sb)))


MATCH, NEAR, MISMATCH, GAP = 2.0, 1.0, -1.0, -1.0


def _score(a: str, b: str) -> float:
    s = similarity(a, b)
    if s == 1.0:
        return MATCH
    if s >= 0.7:
        return NEAR
    return MISMATCH


def _align(t: list[str], q: list[str], expected_offset: int = 0):
    """Local alignment of transcript words t against Qur'an words q.

    Returns (score, t_start, t_end, q_start, q_end, matched) for the best local
    alignment, ends exclusive. ``matched`` counts aligned pairs scoring above zero.

    Ties go to the alignment nearest ``expected_offset`` (q index minus t index):
    where a phrase repeats a few words apart, the window around one occurrence
    also contains the next, and only the seed knows which one this is.
    """
    n, m = len(t), len(q)
    H = [[0.0] * (m + 1) for _ in range(n + 1)]
    best = (0.0, 0, 0)
    for i in range(1, n + 1):
        ti = t[i - 1]
        for j in range(1, m + 1):
            diag = H[i - 1][j - 1] + (_score(ti, q[j - 1]) if ti else GAP)
            h = max(0.0, diag, H[i - 1][j] + GAP, H[i][j - 1] + GAP)
            H[i][j] = h
            if h > best[0] or (h == best[0] > 0 and abs((j - i) - expected_offset) < abs((best[2] - best[1]) - expected_offset)):
                best = (h, i, j)
    score, i, j = best
    t_end, q_end, matched = i, j, 0
    while i > 0 and j > 0 and H[i][j] > 0:
        ti = t[i - 1]
        diag = H[i - 1][j - 1] + (_score(ti, q[j - 1]) if ti else GAP)
        if H[i][j] == diag:
            if ti and _score(ti, q[j - 1]) > 0:
                matched += 1
            i, j = i - 1, j - 1
        elif H[i][j] == H[i - 1][j] + GAP:
            i -= 1
        else:
            j -= 1
    return score, i, t_end, j, q_end, matched


def _others(alternatives: list[Place]) -> str:
    """" (or 27:30)" for a few alternatives; " (or one of 30 other places)" for many."""
    if not alternatives:
        return ""
    if len(alternatives) <= 3:
        return " (or " + ", ".join(p.ref for p in alternatives) + ")"
    return f" (or one of {len(alternatives)} other places)"


class Matcher:
    """Finds quotations. Build once (indexing takes a moment), use many times."""

    def __init__(self, quran: Quran | None = None, min_words: int = 4, min_confidence: float = 0.6):
        self.quran = quran or load()
        self.min_words = min_words
        self.min_confidence = min_confidence
        self.norm = [w.norm for w in self.quran.words]
        self.index: dict[tuple[str, ...], list[int]] = defaultdict(list)
        for i in range(len(self.norm) - SEED + 1):
            self.index[tuple(self.norm[i:i + SEED])].append(i)

    def _place(self, q_start: int, q_end: int) -> Place:
        a, b = self.quran.words[q_start], self.quran.words[q_end - 1]
        return Place((a.sura, a.aya, a.index), (b.sura, b.aya, b.index))

    def _is_partial(self, p: Place) -> bool:
        first = p.start[2] == 0
        last_words = len(tokenize(self.quran.ayah(p.end[0], p.end[1]).simple))
        return not (first and p.end[2] == last_words - 1)

    def find(self, text: str) -> list[Quotation]:
        """Every quotation in ``text``, in order, not overlapping."""
        raw = tokenize(text)
        t = [normalize_word(w) for w in raw]

        # 1. Seeds, grouped by the Qur'an position they imply for transcript word 0.
        diagonals: dict[int, list[int]] = defaultdict(list)
        for i in range(len(t) - SEED + 1):
            gram = tuple(t[i:i + SEED])
            if not all(gram):
                continue
            for qpos in self.index.get(gram, ()):
                diagonals[qpos - i].append(i)

        # 2. Align a window around each group.
        candidates: list[tuple[float, Quotation]] = []
        for diag, hits in diagonals.items():
            t_lo, t_hi = max(0, min(hits) - 8), min(len(t), max(hits) + SEED + 8)
            q_lo = max(0, diag + t_lo - 8)
            q_hi = min(len(self.norm), diag + t_hi + 8)
            score, ts, te, qs, qe, matched = _align(t[t_lo:t_hi], self.norm[q_lo:q_hi], (diag + t_lo) - q_lo)
            if matched < self.min_words:
                continue
            span_q = qe - qs
            confidence = min(1.0, score / (MATCH * max(span_q, te - ts)))
            if confidence < self.min_confidence:
                continue
            place = self._place(q_lo + qs, q_lo + qe)
            candidates.append((score, Quotation(t_lo + ts, t_lo + te, place, round(confidence, 3), matched, partial=self._is_partial(place))))

        # 3. Best first; an equal-scoring candidate over the same span is an alternative place.
        candidates.sort(key=lambda c: (-c[0], c[1].start))
        chosen: list[tuple[float, Quotation]] = []
        for score, cand in candidates:
            same = next((c for s, c in chosen if s == score and (c.start, c.end) == (cand.start, cand.end)), None)
            if same is not None:
                if cand.place != same.place and cand.place not in same.alternatives:
                    same.alternatives.append(cand.place)
                continue
            if any(cand.start < c.end and c.start < cand.end for _, c in chosen):
                continue
            chosen.append((score, cand))
        return sorted((c for _, c in chosen), key=lambda c: c.start)

    def annotate(self, text: str) -> str:
        """The transcript with each quotation replaced by the exact Uthmani text and its reference.

        A partial quotation keeps the speaker's words, marked with the reference,
        because substituting a whole ayah would put words in their mouth.
        """
        raw = tokenize(text)
        out: list[str] = []
        pos = 0
        for qt in self.find(text):
            out.extend(raw[pos:qt.start])
            ref = qt.ref + _others(qt.alternatives)
            if qt.partial:
                out.append(" ".join(raw[qt.start:qt.end]) + f" [{ref}, partial]")
            else:
                (s1, a1, _), (s2, a2, _) = qt.place.start, qt.place.end
                ayat = [a for a in self.quran.ayat if (s1, a1) <= (a.sura, a.aya) <= (s2, a2)]
                out.append("﴿" + " ".join(a.uthmani for a in ayat) + f"﴾ [{ref}]")
            pos = qt.end
        out.extend(raw[pos:])
        return " ".join(out)
