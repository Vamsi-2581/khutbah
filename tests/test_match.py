"""What the matcher must get right, in the shapes speech recognition produces."""

import time

import pytest

from khutbah.match import Matcher, similarity
from khutbah.quran import load, normalize_word


@pytest.fixture(scope="module")
def m():
    return Matcher()


def refs(found):
    return [q.ref for q in found]


def test_the_text_loads_whole():
    q = load()
    assert len(q.ayat) == 6236
    assert sum(a.basmala for a in q.ayat) == 112
    assert q.ayah(2, 1).simple == "الم"  # the printed basmala is held apart
    assert q.ayah(1, 1).simple.startswith("بسم")  # but in al-Fatihah it is the ayah


def test_normalisation_ignores_what_recognition_loses():
    assert normalize_word("ٱلرَّحْمَٰنِ") == normalize_word("الرحمن")
    assert normalize_word("إِلَهَ") == normalize_word("اله")
    assert normalize_word("hello") == ""


def test_a_whole_surah_said_cleanly(m):
    t = "We begin with الحمد لله رب العالمين الرحمن الرحيم مالك يوم الدين اياك نعبد واياك نستعين اهدنا الصراط المستقيم صراط الذين انعمت عليهم غير المغضوب عليهم ولا الضالين and then the khutbah."
    (q,) = m.find(t)
    assert q.ref == "1:2-7"
    assert not q.partial
    assert q.confidence > 0.9


def test_survives_misheard_and_dropped_words(m):
    # Ayat al-Kursi's opening: "al-qayyum" misheard, "sinatun" dropped.
    t = "Allah says الله لا اله الا هو الحي القيوما لا تاخذه ولا نوم له ما في السماوات وما في الارض subhanallah"
    (q,) = m.find(t)
    assert q.ref == "2:255"
    assert q.partial
    assert 0.6 <= q.confidence < 1.0


def test_only_the_quotation_is_marked_in_code_switched_speech(m):
    t = "So brothers, remember that ان الله مع الصابرين as Allah tells us, and be patient."
    (q,) = m.find(t)
    words = t.split()
    assert " ".join(words[q.start:q.end]) == "ان الله مع الصابرين"


def test_arabic_that_is_not_quran_is_not_matched(m):
    # The salawat and a common du'a: Arabic, religious, full of Qur'anic words, not Qur'an.
    assert m.find("اللهم صل على محمد وعلى ال محمد كما صليت على ابراهيم") == []
    assert m.find("جزاكم الله خيرا وبارك الله فيكم") == []


def test_basmala_is_ambiguous_between_its_two_places(m):
    (q,) = m.find("He began بسم الله الرحمن الرحيم and said")
    assert {q.ref, *[a.ref for a in q.alternatives]} == {"1:1", "27:30"}
    assert q.ambiguous


def test_a_repeated_refrain_reports_every_place(m):
    (q,) = m.find("فباي الاء ربكما تكذبان")
    assert len([q.place, *q.alternatives]) == 31


def test_two_quotations_in_one_passage(m):
    t = "قل هو الله احد الله الصمد and also انا اعطيناك الكوثر فصل لربك وانحر ان شانئك هو الابتر"
    assert refs(m.find(t)) == ["112:1-2", "108:1-3"]


def test_annotate_puts_back_the_exact_text_for_whole_ayat(m):
    out = m.annotate("He recited انا اعطيناك الكوثر فصل لربك وانحر ان شانئك هو الابتر today")
    first = load().ayah(108, 1).uthmani
    assert "﴿" + first in out
    assert "[108:1-3]" in out
    assert out.startswith("He recited") and out.endswith("today")


def test_annotate_keeps_the_speakers_words_for_a_partial_ayah(m):
    out = m.annotate("Allah says الله لا اله الا هو الحي القيوم لا تاخذه سنه ولا نوم and so on")
    assert "الله لا اله الا هو الحي القيوم لا تاخذه سنه ولا نوم [2:255, partial]" in out


def test_similarity_is_forgiving_but_not_blind():
    assert similarity("القيوم", "القيوما") >= 0.7
    assert similarity("الصابرين", "الكافرين") < 0.7


def test_indexing_is_fast_enough_to_run_per_process():
    t0 = time.perf_counter()
    Matcher()
    assert time.perf_counter() - t0 < 5
