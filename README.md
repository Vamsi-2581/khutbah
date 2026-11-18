# khutbah

**Speech recognition garbles exactly the Arabic that matters in an English khutbah.** The ayat and the hadith come out as near-misses: words dropped, misheard, run together. Transcripts and captions then misquote the Qur'an, which is worse than leaving it out.

`khutbah` finds every Qur'an quotation in a transcript, even a damaged one, identifies the exact ayat, and puts back the verified text with its reference.

```
$ python -m khutbah annotate talk.txt
… Allah says ﴿إِنَّآ أَعْطَيْنَٰكَ ٱلْكَوْثَرَ فَصَلِّ لِرَبِّكَ وَٱنْحَرْ إِنَّ شَانِئَكَ هُوَ ٱلْأَبْتَرُ﴾ [108:1-3] …
```

## How it works

1. **Seed.** Every run of three transcript words that also occurs in the Qur'an marks a candidate.
2. **Align.** Around each candidate, the transcript and the text are aligned word by word, forgiving a misheard letter or a dropped word, so recognition errors cost a little instead of ending the match.
3. **Decide.** A candidate becomes a quotation only if enough words match and the alignment is good enough. Arabic that isn't Qur'an (the salawat, a du'a) is not matched, even though it's full of Qur'anic words.
4. **Be honest.** Where a phrase occurs in more than one place (the basmala: 1:1 and 27:30; a refrain repeated 31 times in ar-Rahman) every place is reported and the quotation is marked ambiguous, never guessed.
5. **Don't put words in the speaker's mouth.** A whole ayah is replaced with the exact Uthmani text. A partial quotation keeps what was said and gets the reference.

## Try it

```sh
uv run python -m khutbah find talk.txt          # list quotations, with confidence
uv run python -m khutbah find talk.txt --json
uv run python -m khutbah annotate talk.txt      # the transcript with quotations restored
uv run pytest                                   # the tests
```

No dependencies beyond Python 3.10. Indexing the whole Qur'an takes under a second.

## Status

v0: the matcher, for transcripts in Arabic script. Not yet: transliterated Arabic ("innallaha ma'as sabirin"), timestamps (SRT/VTT in, captions out), running speech recognition itself, hadith, and an evaluation set of real khutbahs. Those are open issues, most of them part of [The First Hundred](https://bytheitc.xyz/first-hundred).

## The text

The Qur'an text is the [Tanzil](https://tanzil.net) Quran Text (Simple Clean for matching, Uthmani for display), used verbatim under its terms. Tanzil's files carry the printed basmala inside the first ayah of 112 surahs; `khutbah` holds it apart in memory, because it is an ayah in its own right only in 1:1 and 27:30. The files themselves are unchanged.
