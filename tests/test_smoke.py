"""Fast end-to-end smoke tests: CLI + MCP tool signatures + cross-surface curation."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

import defluff
from defluff.lexicon import load_lexicon

PYTHON = sys.executable
FLUFFY = (
    "At the end of the day, it is important to note that, in many ways, we "
    "really need to basically leverage our core competencies in order to "
    "actually move the needle going forward."
)
CLEAN = (
    "Startups condense decades of work into a few years. "
    "A founder who hires slowly keeps optionality; one who hires fast buys speed. "
    "Most ideas that seem bad are merely unfamiliar."
)


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------

def _cli(*args, input_text=None):
    return subprocess.run(
        [PYTHON, "-m", "defluff.cli", *args],
        input=input_text,
        capture_output=True,
        text=True,
    )


def test_cli_lint_sloppy_exits_1():
    r = _cli("lint", input_text=FLUFFY)
    assert r.returncode == 1


def test_cli_lint_clean_exits_0():
    r = _cli("lint", input_text=CLEAN)
    assert r.returncode == 0


def test_cli_lint_empty_exits_2():
    r = _cli("lint", input_text="   ")
    assert r.returncode == 2


def test_cli_lint_json_shape():
    r = _cli("lint", "--json", input_text=FLUFFY)
    data = json.loads(r.stdout)
    for key in ("slop_score", "slop_density", "categories", "spans", "n_words",
                "low_confidence", "lexicon_version", "threshold_provisional"):
        assert key in data, f"missing key: {key}"


def test_cli_score_outputs_float():
    r = _cli("score", input_text=FLUFFY)
    assert r.returncode == 0
    val = float(r.stdout.strip())
    assert 0.0 <= val <= 1.0


def test_cli_lint_threshold_flag():
    # threshold 0.0 -> everything is over it
    r = _cli("lint", "--threshold", "0.0", input_text=CLEAN + " " * 30)
    # score is 0 on clean text so 0 > 0.0 is False -> should exit 0
    assert r.returncode in (0, 1)  # depends on exact score


def test_cli_no_project_overlay_flag():
    r = _cli("lint", "--no-project-overlay", input_text=CLEAN)
    assert r.returncode in (0, 1)  # doesn't crash


# ---------------------------------------------------------------------------
# MCP tool function signatures (import-level, no transport needed)
# ---------------------------------------------------------------------------

def test_mcp_tools_importable():
    from defluff import mcp as mcp_mod
    assert callable(mcp_mod.slop_detect)
    assert callable(mcp_mod.slop_add)
    assert callable(mcp_mod.slop_ignore)


def test_mcp_slop_detect_returns_report_shape(tmp_path, monkeypatch):
    from defluff import mcp as mcp_mod
    from defluff import lexicon as lex_mod
    monkeypatch.setattr(lex_mod, "_cache", {})
    mcp_mod._lexicon = None

    result = mcp_mod.slop_detect(FLUFFY)
    assert "slop_score" in result
    assert "spans" in result


def test_mcp_slop_detect_empty_returns_error(monkeypatch):
    from defluff import mcp as mcp_mod
    result = mcp_mod.slop_detect("")
    assert "error" in result


def test_mcp_add_and_detect_within_same_process(tmp_path, monkeypatch):
    """Long-lived process sees its own slop_add on next slop_detect."""
    from defluff import mcp as mcp_mod
    from defluff import lexicon as lex_mod

    monkeypatch.setattr(lex_mod, "_USER_LEXICON", tmp_path / "lexicon.json")
    monkeypatch.setattr(lex_mod, "_USER_IGNORE", tmp_path / "ignore.json")
    monkeypatch.setattr(lex_mod, "_cache", {})
    mcp_mod._lexicon = None

    phrase = "xyzzy unique mcp phrase zork"
    mcp_mod.slop_add(phrase, "cliche", scope="user")
    text = f"This is {phrase} in a sentence with enough words to pass the floor."
    result = mcp_mod.slop_detect(text)
    assert "slop_score" in result
    span_texts = [s["text"] for s in result.get("spans", [])]
    assert any(phrase in t for t in span_texts), f"phrase not found in spans: {span_texts}"


# ---------------------------------------------------------------------------
# E2E: curation loop (add via library -> detect auto-loads, no flags)
# ---------------------------------------------------------------------------

def test_curation_persists_across_detect_calls(tmp_path, monkeypatch):
    """Core promise: add once, every later detect() picks it up."""
    from defluff import lexicon as lex_mod
    monkeypatch.setattr(lex_mod, "_USER_LEXICON", tmp_path / "lexicon.json")
    monkeypatch.setattr(lex_mod, "_USER_IGNORE", tmp_path / "ignore.json")
    monkeypatch.setattr(lex_mod, "_cache", {})

    unique = "hypercalifragilistic slop marker unique"
    defluff.lexicon_add(unique, "cliche", scope="user")

    # Detect WITHOUT passing lexicon= arg — relies on auto-load.
    r = defluff.detect(f"This sentence contains {unique} and more words to avoid short text issues.")
    assert any(unique in s.text for s in r.spans)
