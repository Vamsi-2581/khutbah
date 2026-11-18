"""python -m khutbah find|annotate <transcript.txt | ->  [--json]"""

from __future__ import annotations

import argparse
import json
import sys

from .match import Matcher


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="khutbah", description="Find Qur'an quotations in a khutbah transcript.")
    p.add_argument("command", choices=["find", "annotate"])
    p.add_argument("transcript", help="a text file, or - for standard input")
    p.add_argument("--json", action="store_true", help="machine-readable output (find)")
    args = p.parse_args(argv)

    text = sys.stdin.read() if args.transcript == "-" else open(args.transcript, encoding="utf-8").read()
    m = Matcher()
    if args.command == "annotate":
        print(m.annotate(text))
        return 0

    words = text.split()
    found = m.find(text)
    if args.json:
        print(json.dumps([{
            "start": q.start, "end": q.end, "ref": q.ref, "confidence": q.confidence, "partial": q.partial,
            "alternatives": [a.ref for a in q.alternatives], "said": " ".join(words[q.start:q.end]),
        } for q in found], ensure_ascii=False, indent=2))
        return 0
    if not found:
        print("No Qur'an quotations found.")
    for q in found:
        alt = ("  (also " + ", ".join(a.ref for a in q.alternatives[:3]) + (f" and {len(q.alternatives) - 3} more" if len(q.alternatives) > 3 else "") + ")") if q.ambiguous else ""
        print(f"{q.ref:>12}  {q.confidence:.2f}{'  partial' if q.partial else ''}{alt}\n              {' '.join(words[q.start:q.end])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
