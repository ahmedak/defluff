"""Public API: detect, score, is_slop, lexicon_add, lexicon_ignore.

All three scoring functions accept an optional `lexicon=` handle (from
load_lexicon()) to pin the resolved lexicon for reproducible reward loops.
Without it, an mtime-keyed process-level cache auto-loads and rebuilds only
when an overlay file changes.
"""

from __future__ import annotations

from .lexicon import (
    Lexicon,
    LexiconNotFoundError,
    PackNotFoundError,
    get_default_lexicon,
    lexicon_add,
    lexicon_ignore,
    lexicon_list,
    list_packs,
    load_lexicon,
)
from .preprocess import clean
from .report import SlopReport, build_slop_report, to_human, to_json


def detect(
    text: str,
    *,
    lexicon: Lexicon | None = None,
) -> SlopReport:
    """Full slop analysis. Returns SlopReport with score, spans, and categories.

    Pass lexicon=load_lexicon() to pin the resolved lexicon (required for
    reproducible reward/RL loops where an overlay may change mid-run).
    """
    if not text or not text.strip():
        raise ValueError("text must not be empty or whitespace-only")
    cleaned = clean(text)
    lex = lexicon if lexicon is not None else get_default_lexicon()
    return build_slop_report(cleaned, lex)


def score(
    text: str,
    *,
    lexicon: Lexicon | None = None,
) -> float:
    """Return the bare slop_score in [0, 1]. For reward/ranking loops.

    For an unclamped gradient-preserving value, use detect().slop_density.
    """
    return detect(text, lexicon=lexicon).slop_score


def compare(
    text_a: str,
    text_b: str,
    *,
    lexicon: Lexicon | None = None,
) -> dict:
    """Compare two texts and return which improved, which regressed, and the score delta.

    Returns a dict with keys:
      score_a, score_b, delta (b - a),
      improved (spans in a not in b), regressed (new spans in b not in a).
    Useful in revision loops: distinguish 'you removed sloppy content' from 'you rewrote it'.
    """
    lex = lexicon if lexicon is not None else get_default_lexicon()
    r_a = build_slop_report(clean(text_a), lex)
    r_b = build_slop_report(clean(text_b), lex)
    patterns_a = {s.text.lower() for s in r_a.spans}
    patterns_b = {s.text.lower() for s in r_b.spans}
    return {
        "score_a": r_a.slop_score,
        "score_b": r_b.slop_score,
        "delta": round(r_b.slop_score - r_a.slop_score, 4),
        "improved": sorted(patterns_a - patterns_b),
        "regressed": sorted(patterns_b - patterns_a),
    }


def is_slop(
    text: str,
    *,
    threshold: float | None = None,
    lexicon: Lexicon | None = None,
) -> bool:
    """Gate convenience: True if slop_score > threshold.

    threshold defaults to the value in the bundled lexicon data
    (currently provisional; check SlopReport.threshold_provisional).
    """
    lex = lexicon if lexicon is not None else get_default_lexicon()
    t = threshold if threshold is not None else lex.meta.default_threshold
    return score(text, lexicon=lex) > t


__all__ = [
    "detect",
    "score",
    "is_slop",
    "compare",
    "load_lexicon",
    "lexicon_add",
    "lexicon_ignore",
    "lexicon_list",
    "list_packs",
    "Lexicon",
    "SlopReport",
    "LexiconNotFoundError",
    "PackNotFoundError",
    "to_json",
    "to_human",
]
