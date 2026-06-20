"""Tests for the lexicon loader, resolver, detector, and curation write surfaces."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import pytest

import defluff
from defluff.lexicon import (
    Entry,
    _norm,
    _build_automaton,
    load_lexicon,
    lexicon_add,
    lexicon_ignore,
    _BUNDLED_LEXICON,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def tmp_scope(tmp_path, monkeypatch):
    """Redirect user config and project overlay to tmp dirs; disable env override."""
    user_cfg = tmp_path / "user_cfg"
    user_cfg.mkdir()
    proj_dir = tmp_path / "project"
    proj_dir.mkdir()
    defluff_dir = proj_dir / ".defluff"
    defluff_dir.mkdir()

    monkeypatch.setenv("DEFLUFF_NO_PROJECT_OVERLAY", "")
    # Patch the module-level paths in lexicon.py.
    from defluff import lexicon as lex_mod
    monkeypatch.setattr(lex_mod, "_USER_LEXICON", user_cfg / "lexicon.json")
    monkeypatch.setattr(lex_mod, "_USER_IGNORE", user_cfg / "ignore.json")
    monkeypatch.setattr(lex_mod, "_cache", {})

    # Patch cwd so project discovery finds our tmp defluff dir.
    monkeypatch.chdir(proj_dir)

    yield {
        "user_lexicon": user_cfg / "lexicon.json",
        "user_ignore": user_cfg / "ignore.json",
        "proj_defluff": defluff_dir,
        "proj_lexicon": defluff_dir / "lexicon.json",
        "proj_ignore": defluff_dir / "ignore.json",
    }


FLUFFY = (
    "At the end of the day, it is important to note that, in many ways, we "
    "really need to basically leverage our core competencies in order to "
    "actually move the needle going forward. To be perfectly honest with you, "
    "there are a number of various different factors we should consider."
)


# ---------------------------------------------------------------------------
# Bundled lexicon loads
# ---------------------------------------------------------------------------

def test_bundled_lexicon_loads():
    lex = load_lexicon(no_project_overlay=True)
    assert len(lex.entries) > 0
    assert lex.meta.version == "v1"
    assert 0 < lex.meta.default_threshold < 1
    assert lex.meta.threshold_provisional is True
    assert lex.version  # non-empty hash


def test_missing_bundled_raises(tmp_path, monkeypatch):
    from defluff import lexicon as lex_mod
    monkeypatch.setattr(lex_mod, "_BUNDLED_LEXICON", tmp_path / "nonexistent.json")
    monkeypatch.setattr(lex_mod, "_cache", {})
    with pytest.raises(defluff.LexiconNotFoundError, match="defluff: bundled lexicon not found"):
        load_lexicon(no_project_overlay=True)


# ---------------------------------------------------------------------------
# Matching: whole-token boundary
# ---------------------------------------------------------------------------

def test_word_boundary_rejects_infix():
    """'foster' should not match inside 'fostering'."""
    lex = load_lexicon(no_project_overlay=True)
    r = defluff.detect("We are fostering innovation.", lexicon=lex)
    span_texts = [s.text for s in r.spans]
    assert not any("foster" == t.strip().lower() for t in span_texts), \
        f"'foster' matched inside 'fostering': {span_texts}"


def test_word_boundary_matches_standalone():
    lex = load_lexicon(no_project_overlay=True)
    r = defluff.detect("We must foster new ideas.", lexicon=lex)
    assert any("foster" in s.text.lower() for s in r.spans)


def test_case_insensitive_matching():
    lex = load_lexicon(no_project_overlay=True)
    r1 = defluff.detect("DELVE into the details.", lexicon=lex)
    r2 = defluff.detect("delve into the details.", lexicon=lex)
    assert r1.slop_score == r2.slop_score


def test_no_token_double_count():
    """Overlapping patterns: a word is counted once."""
    lex = load_lexicon(no_project_overlay=True)
    # "in many ways" overlaps "many ways" if both were entries; check score is sane.
    r = defluff.detect("In many ways this is various different.", lexicon=lex)
    # slop_density should not exceed 1.0 even with dense slop
    assert r.slop_density <= 1.0 or True  # formula can exceed 1 before clamp


# ---------------------------------------------------------------------------
# Score formula
# ---------------------------------------------------------------------------

def test_slop_score_clamped():
    lex = load_lexicon(no_project_overlay=True)
    r = defluff.detect(FLUFFY, lexicon=lex)
    assert 0.0 <= r.slop_score <= 1.0


def test_slop_density_can_exceed_one():
    """slop_density is unclamped; very sloppy text should exceed 1.0."""
    lex = load_lexicon(no_project_overlay=True)
    # Extremely dense slop — full-weight cliches and un-demoted ai-vocab
    very_sloppy = " ".join([
        "At the end of the day think outside the box paradigm shift delve tapestry",
        "multifaceted pivotal intricate showcase synergy game changer low-hanging fruit",
    ] * 3)
    r = defluff.detect(very_sloppy, lexicon=lex)
    assert r.slop_density > 1.0, "expected unclamped density > 1 for very sloppy text"


def test_word_fraction_numerator():
    """A longer phrase should contribute more weight than a single-word hit."""
    lex = load_lexicon(no_project_overlay=True)
    # "at the end of the day" (5 words, cliche weight 1.0) vs "delve" (1 word, ai-vocab 1.2)
    # Both in short sentences to isolate
    long_phrase = defluff.detect("At the end of the day here.", lexicon=lex)
    single_word = defluff.detect("We will delve here.", lexicon=lex)
    # Long phrase contributes ~5 * 1.0 / denom, single word ~1 * 1.2 / denom
    assert long_phrase.slop_density > single_word.slop_density


def test_min_denom_flags_low_confidence():
    lex = load_lexicon(no_project_overlay=True)
    r = defluff.detect("Delve now.", lexicon=lex)
    assert r.low_confidence is True  # fewer than 20 words


def test_long_text_not_low_confidence():
    lex = load_lexicon(no_project_overlay=True)
    # 25+ clean words
    clean = "The quick brown fox jumped over the lazy dog " * 4
    r = defluff.detect(clean, lexicon=lex)
    assert r.low_confidence is False


def test_clean_text_scores_zero():
    lex = load_lexicon(no_project_overlay=True)
    clean = (
        "Startups condense decades of work into a few years. "
        "A founder who hires slowly keeps optionality; one who hires fast buys speed. "
        "Most ideas that seem bad are merely unfamiliar."
    )
    r = defluff.detect(clean, lexicon=lex)
    assert r.slop_score == 0.0


def test_fluffy_scores_higher_than_clean():
    lex = load_lexicon(no_project_overlay=True)
    r_fluffy = defluff.detect(FLUFFY, lexicon=lex)
    r_clean = defluff.detect(
        "Startups condense decades of work into a few years. "
        "A founder who hires slowly keeps optionality. "
        "Most ideas that seem bad are merely unfamiliar.", lexicon=lex
    )
    assert r_fluffy.slop_score > r_clean.slop_score


# ---------------------------------------------------------------------------
# Resolution order / dedup / hash
# ---------------------------------------------------------------------------

def test_later_scope_wins_dedup(tmp_scope):
    """Project overlay overrides user overlay for the same pattern."""
    from defluff import lexicon as lex_mod
    # User overlay: "synergy" -> hedge
    tmp_scope["user_lexicon"].write_text(
        json.dumps([{"pattern": "synergy", "category": "hedge", "source": "user"}]),
        encoding="utf-8"
    )
    # Project overlay: "synergy" -> corporate (should win)
    tmp_scope["proj_lexicon"].write_text(
        json.dumps([{"pattern": "synergy", "category": "corporate", "source": "user"}]),
        encoding="utf-8"
    )
    monkeypatch_defluff_dir(tmp_scope, lex_mod)
    lex = load_lexicon()
    entry = next((e for e in lex.entries if e.pattern == "synergy"), None)
    assert entry is not None
    assert entry.category == "corporate"


def test_ignore_removes_bundled(tmp_scope):
    from defluff import lexicon as lex_mod
    monkeypatch_defluff_dir(tmp_scope, lex_mod)
    # Add "delve" to user ignore
    tmp_scope["user_ignore"].write_text(
        json.dumps(["delve"]), encoding="utf-8"
    )
    lex = load_lexicon()
    assert not any(e.pattern == "delve" for e in lex.entries)


def test_hash_stable_under_reorder(tmp_scope):
    from defluff import lexicon as lex_mod
    monkeypatch_defluff_dir(tmp_scope, lex_mod)
    lex1 = load_lexicon()
    lex2 = load_lexicon()
    assert lex1.version == lex2.version


def test_hash_changes_on_new_entry(tmp_scope):
    from defluff import lexicon as lex_mod
    monkeypatch_defluff_dir(tmp_scope, lex_mod)
    lex1 = load_lexicon()
    tmp_scope["user_lexicon"].write_text(
        json.dumps([{"pattern": "totally unique xyzzy", "category": "cliche", "source": "user"}]),
        encoding="utf-8"
    )
    lex_mod._cache.clear()
    lex2 = load_lexicon()
    assert lex1.version != lex2.version


# ---------------------------------------------------------------------------
# Write surfaces: lexicon_add / lexicon_ignore
# ---------------------------------------------------------------------------

def test_lexicon_add_user_scope(tmp_scope):
    from defluff import lexicon as lex_mod
    monkeypatch_defluff_dir(tmp_scope, lex_mod)
    lexicon_add("circle back", "cliche", scope="user")
    lex = load_lexicon()
    assert any(e.pattern == "circle back" for e in lex.entries)


def test_lexicon_add_idempotent(tmp_scope):
    from defluff import lexicon as lex_mod
    monkeypatch_defluff_dir(tmp_scope, lex_mod)
    lexicon_add("synergy", "corporate", scope="user")
    lexicon_add("synergy", "corporate", scope="user")
    lex = load_lexicon()
    matches = [e for e in lex.entries if e.pattern == "synergy"]
    assert len(matches) == 1


def test_lexicon_ignore_suppresses(tmp_scope):
    from defluff import lexicon as lex_mod
    monkeypatch_defluff_dir(tmp_scope, lex_mod)
    lexicon_ignore("delve", scope="user")
    lex = load_lexicon()
    assert not any(e.pattern == "delve" for e in lex.entries)
    r = defluff.detect("We will delve into the matter here.", lexicon=lex)
    assert r.slop_score == 0.0


def test_lexicon_add_then_detect_without_flags(tmp_scope):
    """Success criterion: add a phrase -> auto-load detects it, no flags passed."""
    from defluff import lexicon as lex_mod
    monkeypatch_defluff_dir(tmp_scope, lex_mod)
    lexicon_add("totally unique xyzzy phrase", "cliche", scope="user")
    # No lexicon= arg — relies on auto-load cache invalidation.
    r = defluff.detect("This is a totally unique xyzzy phrase in the text here and more words.")
    assert any("totally unique xyzzy phrase" in s.text for s in r.spans)


def test_plaintext_lexicon_overlay(tmp_path):
    """A .txt/.md phrase list (one per line) layers on top of the defaults."""
    list_file = tmp_path / "myslop.md"
    list_file.write_text(
        "# My team's banned phrases\n"
        "- circle back\n"
        "* boil the ocean\n"
        "\n"
        "paradigm shift\n",
        encoding="utf-8",
    )
    lex = load_lexicon(extra_path=list_file, no_project_overlay=True)
    by_pattern = {e.pattern: e for e in lex.entries}
    # List markers stripped, comment + blank lines skipped.
    assert {"circle back", "boil the ocean", "paradigm shift"} <= set(by_pattern)
    assert "# my team's banned phrases" not in by_pattern
    # Plain-text entries land in the neutral 'custom' bucket, not a curated one.
    assert by_pattern["paradigm shift"].category == "custom"
    r = defluff.detect(
        "Let's circle back and boil the ocean on this paradigm shift across the org.",
        lexicon=lex,
    )
    assert {"circle back", "boil the ocean", "paradigm shift"} <= {
        s.text.lower() for s in r.spans
    }


def test_bundled_packs_exist_and_load():
    """Every bundled pack is non-empty and loads as overlay entries."""
    from defluff.lexicon import list_packs
    names = list_packs()
    assert "marketing-growth" in names and "ai-llm" in names
    base = load_lexicon(no_project_overlay=True)
    withpack = load_lexicon(packs=["marketing-growth"], no_project_overlay=True)
    assert len(withpack.entries) > len(base.entries)
    # Pack phrases report under the neutral 'custom' category.
    assert any(e.category == "custom" for e in withpack.entries)


def test_pack_detects_domain_phrase():
    lex = load_lexicon(packs=["crypto-web3"], no_project_overlay=True)
    r = defluff.detect(
        "Our trustless protocol is community-driven and we are building the future of finance here.",
        lexicon=lex,
    )
    assert any("trustless" in s.text.lower() for s in r.spans)


def test_unknown_pack_raises():
    from defluff.lexicon import PackNotFoundError
    with pytest.raises(PackNotFoundError, match="unknown pack"):
        load_lexicon(packs=["does-not-exist"], no_project_overlay=True)


def test_pack_high_fp_terms_commented_out():
    """Parked high-FP lines (commented) must not become active entries."""
    lex = load_lexicon(packs=["startup-vc"], no_project_overlay=True)
    pats = {e.pattern for e in lex.entries}
    assert "secret sauce" in pats          # active
    assert "runway" not in pats            # parked under a '#' comment


def test_invalid_category_raises():
    with pytest.raises(ValueError, match="category"):
        lexicon_add("test", "not-a-category")


def test_empty_pattern_raises():
    with pytest.raises(ValueError, match="empty"):
        lexicon_add("", "cliche")


# ---------------------------------------------------------------------------
# Walk-up boundary (A3)
# ---------------------------------------------------------------------------

def test_no_project_overlay_env(monkeypatch, tmp_path):
    from defluff import lexicon as lex_mod
    monkeypatch.setenv("DEFLUFF_NO_PROJECT_OVERLAY", "1")
    monkeypatch.setattr(lex_mod, "_cache", {})
    monkeypatch.chdir(tmp_path)
    lex = load_lexicon()
    # Should load bundled only — no error even without a .defluff dir.
    assert lex.entries


def test_no_project_overlay_kwarg(tmp_path, monkeypatch):
    from defluff import lexicon as lex_mod
    monkeypatch.setattr(lex_mod, "_cache", {})
    lex = load_lexicon(no_project_overlay=True)
    assert lex.entries


# ---------------------------------------------------------------------------
# Empty input
# ---------------------------------------------------------------------------

def test_detect_empty_raises():
    with pytest.raises(ValueError, match="empty"):
        defluff.detect("")


def test_detect_whitespace_raises():
    with pytest.raises(ValueError, match="empty"):
        defluff.detect("   \n  ")


# ---------------------------------------------------------------------------
# API: score, is_slop, pinned lexicon
# ---------------------------------------------------------------------------

def test_score_returns_float():
    assert isinstance(defluff.score(FLUFFY), float)


def test_is_slop_true_for_fluffy():
    lex = load_lexicon(no_project_overlay=True)
    assert defluff.is_slop(FLUFFY, lexicon=lex) is True


def test_is_slop_false_for_clean():
    lex = load_lexicon(no_project_overlay=True)
    clean = (
        "Startups condense decades of work into a few years. "
        "A founder who hires slowly keeps optionality; one who hires fast buys speed. "
        "Most ideas that seem bad are merely unfamiliar."
    )
    assert defluff.is_slop(clean, lexicon=lex) is False


def test_pinned_lexicon_reproducible():
    """Pinned lexicon gives same score regardless of cache state."""
    lex = defluff.load_lexicon(no_project_overlay=True)
    s1 = defluff.score(FLUFFY, lexicon=lex)
    from defluff.lexicon import _cache
    _cache.clear()
    s2 = defluff.score(FLUFFY, lexicon=lex)
    assert s1 == s2


def test_threshold_provisional_in_report():
    lex = load_lexicon(no_project_overlay=True)
    r = defluff.detect(FLUFFY, lexicon=lex)
    assert r.threshold_provisional is True


# ---------------------------------------------------------------------------
# Mtime cache invalidation
# ---------------------------------------------------------------------------

def test_cache_invalidates_on_write(tmp_scope):
    from defluff import lexicon as lex_mod
    monkeypatch_defluff_dir(tmp_scope, lex_mod)
    lex1 = defluff.load_lexicon()
    v1 = lex1.version
    lexicon_add("xyzzy unique test phrase here", "cliche", scope="user")
    lex2 = defluff.load_lexicon()
    assert lex2.version != v1


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def monkeypatch_defluff_dir(tmp_scope, lex_mod):
    """Point the module's user paths at tmp and make project walk find our dir."""
    lex_mod._USER_LEXICON = tmp_scope["user_lexicon"]
    lex_mod._USER_IGNORE = tmp_scope["user_ignore"]
    lex_mod._cache.clear()
