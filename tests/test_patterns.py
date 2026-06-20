"""Tests for the regex 'rhetoric' pattern layer (antithesis detection)."""

from __future__ import annotations

import defluff
from defluff.lexicon import load_lexicon
from defluff.patterns import RHETORIC_CATEGORY, load_patterns

# Compound antithesis — flagged by default.
COMPOUND = (
    "It is not about origin, it is about quality. "
    "Your list isn't a competitor — it's the input. "
    "We built not just a list but a runtime."
)
# Fragment antithesis — only flagged when the opt-in tier is on.
FRAGMENT = "The lexicon is versioned, not frozen. This is a signal, not a verdict."
# Legitimate contrasts the fragment lookahead must NOT flag.
LEGIT = (
    "Chosen by hand, not yet calibrated. We gate on the categories you trust, "
    "not all five. A lower score means less filler, not necessarily better writing."
)


def _rhetoric_spans(report):
    return [s for s in report.spans if RHETORIC_CATEGORY in s.categories]


# ---------------------------------------------------------------------------
# Default tier: compounds on, fragment off
# ---------------------------------------------------------------------------

def test_compound_flagged_by_default():
    r = defluff.detect(COMPOUND, lexicon=load_lexicon(no_project_overlay=True))
    spans = _rhetoric_spans(r)
    assert len(spans) >= 3, [s.text for s in spans]
    assert RHETORIC_CATEGORY in r.categories


def test_fragment_not_flagged_by_default():
    r = defluff.detect(FRAGMENT, lexicon=load_lexicon(no_project_overlay=True))
    assert _rhetoric_spans(r) == []


# ---------------------------------------------------------------------------
# Opt-in fragment tier
# ---------------------------------------------------------------------------

def test_fragment_flagged_when_opted_in():
    lex = load_lexicon(no_project_overlay=True, rhetoric_fragments=True)
    r = defluff.detect(FRAGMENT, lexicon=lex)
    texts = [s.text.lower() for s in _rhetoric_spans(r)]
    assert any("versioned, not frozen" in t for t in texts), texts
    assert any("signal, not a verdict" in t for t in texts), texts


def test_fragment_lookahead_excludes_legit_contrasts():
    """'not yet' / 'not all' / 'not necessarily' are adverbial, not antithesis."""
    lex = load_lexicon(no_project_overlay=True, rhetoric_fragments=True)
    r = defluff.detect(LEGIT, lexicon=lex)
    assert _rhetoric_spans(r) == [], [s.text for s in _rhetoric_spans(r)]


# ---------------------------------------------------------------------------
# Scoring: a long construction counts once (fixed weight)
# ---------------------------------------------------------------------------

def test_pattern_uses_fixed_weight_not_per_word():
    text = (
        "It is not about the origin of the text, it is about the quality here. "
        + "word " * 30
    )
    r = defluff.detect(text, lexicon=load_lexicon(no_project_overlay=True))
    spans = _rhetoric_spans(r)
    assert len(spans) == 1
    span = spans[0]
    # The construction covers many words but contributes a single fixed unit of
    # weight — a long antithesis cannot dominate the density score per-word.
    assert len(span.text.split()) > 5
    assert span.weight == 1.0


# ---------------------------------------------------------------------------
# Pinning: enabling the fragment tier changes the lexicon hash
# ---------------------------------------------------------------------------

def test_fragment_tier_changes_version_hash():
    base = load_lexicon(no_project_overlay=True)
    opted = load_lexicon(no_project_overlay=True, rhetoric_fragments=True)
    assert base.version != opted.version


def test_load_patterns_optin_gating():
    assert all(not p.optin for p in load_patterns(include_optin=False))
    assert any(p.optin for p in load_patterns(include_optin=True))
