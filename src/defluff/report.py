"""SlopReport + span detection + score formula.

Score formula:
  num = sum(flagged_word_count * category_weight[c]) over matched spans
  slop_score = clamp01(num / max(n_words, MIN_DENOM))
  slop_density = num / max(n_words, MIN_DENOM)  -- raw, unclamped, for reward loops

MIN_DENOM = 20: short-text floor that defeats the single-phrase step-function
on texts < 20 words (low_confidence=True).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .patterns import find_pattern_matches

if TYPE_CHECKING:
    from .lexicon import Lexicon

MIN_DENOM = 20
_TOKEN_RE = re.compile(r"\b\w+\b")


def _snippet(text: str, max_len: int = 70) -> str:
    return text if len(text) <= max_len else text[:max_len - 3] + "..."


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class Span:
    start: int            # char offset in original text
    end: int
    text: str
    categories: list[str]
    weight: float         # sum of category_weight * word_count for this span


@dataclass
class SlopReport:
    slop_score: float                      # clamped [0,1]
    slop_density: float                    # raw unclamped (for reward loops)
    categories: dict[str, float]           # per-category slop_density contribution
    spans: list[Span]
    n_words: int
    low_confidence: bool                   # True when n_words < MIN_DENOM
    lexicon_version: str
    threshold_provisional: bool

    # Convenience
    def above_threshold(self, threshold: float) -> bool:
        return self.slop_score > threshold

    def spans_by_weight(self) -> list[Span]:
        """Return spans sorted by per-span weight descending — highest-impact hits first."""
        return sorted(self.spans, key=lambda s: s.weight, reverse=True)

    def spans_for_category(self, category: str) -> list[Span]:
        """Return only spans matching a given category."""
        return [s for s in self.spans if category in s.categories]


# ---------------------------------------------------------------------------
# Detection from a Lexicon
# ---------------------------------------------------------------------------

def detect_spans(
    text: str,
    lexicon: Lexicon,
) -> tuple[list[Span], int, dict[str, float]]:
    """Run the lexicon detector. Returns (spans, n_words, category_densities).

    Matching rules:
    - Whole-token boundary enforced in lexicon.find_matches()
    - Regex 'rhetoric' patterns merged into the same pipeline; they carry
      fixed_weight=True so a construction counts once, not per covered word
    - Overlap: longest-match-wins via greedy left-to-right merge
    - A word token is counted once (no cross-category double-count)
    - Score numerator = sum(per-span weight)
    """
    words = _TOKEN_RE.findall(text)
    n_words = len(words)
    cat_weights = lexicon.meta.category_weights

    raw_hits = lexicon.find_matches(text) + find_pattern_matches(text, lexicon.patterns)
    if not raw_hits:
        return [], n_words, {}

    # Sort by start offset, then by longest span first (longest-match-wins).
    raw_hits.sort(key=lambda h: (h["start"], -(h["end"] - h["start"])))

    # Greedy merge: consume hits left-to-right, skip those that overlap a
    # previously accepted span (longest-wins since sorted descending by length).
    accepted: list[dict] = []
    last_end = -1
    for hit in raw_hits:
        if hit["start"] >= last_end:
            accepted.append(hit)
            last_end = hit["end"]

    # Convert char-spans back to word-token spans using a word-offset map.
    # Build: for each word token, record its char start.
    word_starts: list[int] = []
    for m in _TOKEN_RE.finditer(text):
        word_starts.append(m.start())

    # Map each accepted char-span to a set of word indices it covers.
    flagged_words: set[int] = set()
    spans: list[Span] = []
    cat_weight_sums: dict[str, float] = {}

    for hit in accepted:
        # Find word indices covered by this char span.
        covered = [
            i for i, ws in enumerate(word_starts)
            if ws >= hit["start"] and ws < hit["end"]
        ]
        if not covered:
            continue
        wcount = len(covered)
        flagged_words.update(covered)
        cat = hit["category"]

        # Lexicon hits weigh per flagged word; regex pattern hits carry a fixed
        # weight per construction (fixed_weight) so a long "it's not X, it's Y"
        # can't dominate the density score.
        base = hit["weight"] if hit["weight"] is not None else cat_weights.get(cat, 1.0)
        w = base if hit.get("fixed_weight") else base * wcount
        cat_weight_sums[cat] = cat_weight_sums.get(cat, 0.0) + w

        # Span text from original: char slice.
        span_text = text[hit["start"]:hit["end"]]
        spans.append(Span(
            start=hit["start"],
            end=hit["end"],
            text=span_text,
            categories=[cat],
            weight=w,
        ))

    denom = max(n_words, MIN_DENOM)
    cat_densities = {
        cat: round(weight_sum / denom, 4)
        for cat, weight_sum in cat_weight_sums.items()
    }

    return spans, n_words, cat_densities


def build_slop_report(
    text: str,
    lexicon: Lexicon,
) -> SlopReport:
    """Build a SlopReport from text and a resolved Lexicon."""
    spans, n_words, cat_densities = detect_spans(text, lexicon)
    denom = max(n_words, MIN_DENOM)
    raw_num = sum(s.weight for s in spans)
    slop_density = raw_num / denom
    slop_score = min(1.0, slop_density)

    return SlopReport(
        slop_score=round(slop_score, 4),
        slop_density=round(slop_density, 4),
        categories=cat_densities,
        spans=sorted(spans, key=lambda s: s.start),
        n_words=n_words,
        low_confidence=n_words < MIN_DENOM,
        lexicon_version=lexicon.version,
        threshold_provisional=lexicon.meta.threshold_provisional,
    )


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------

def to_json(r: SlopReport) -> dict:
    return {
        "slop_score": r.slop_score,
        "slop_density": r.slop_density,
        "categories": r.categories,
        "spans": [
            {"start": s.start, "end": s.end, "text": s.text,
             "categories": s.categories, "weight": s.weight}
            for s in r.spans
        ],
        "n_words": r.n_words,
        "low_confidence": r.low_confidence,
        "lexicon_version": r.lexicon_version,
        "threshold_provisional": r.threshold_provisional,
    }


def to_human(r: SlopReport, threshold: float | None = None) -> str:
    # Lead with the highlighted spans (the robust signal); the single-number
    # summary is intentionally demoted to a quiet footer.
    lines: list[str] = []
    if r.spans:
        lines.append("slop spans:")
        for s in r.spans:
            cat_label = ",".join(s.categories)
            lines.append(f"  [{cat_label}] {_snippet(s.text)}")
    else:
        lines.append("no slop spans found")

    lines.append("")
    pct = int(round(r.slop_score * 100))
    verdict = "OVER THRESHOLD" if (threshold and r.slop_score > threshold) else "OK"
    conf_note = " [low confidence — short text]" if r.low_confidence else ""
    lines.append(f"slop: {pct}%  ({r.slop_score:.3f})  {verdict}{conf_note}")
    if r.categories:
        cat_str = "  ".join(f"{c}:{v:.3f}" for c, v in sorted(r.categories.items()))
        lines.append(f"categories: {cat_str}")
    lines.append(f"lexicon: {r.lexicon_version}" +
                 (" [threshold provisional]" if r.threshold_provisional else ""))
    return "\n".join(lines)
