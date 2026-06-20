"""Regex 'structural pattern' layer — catches rhetorical *constructions* that
aren't fixed phrases, so they can't live in the literal Aho-Corasick lexicon.

The flagship is the antithesis tell:
  - compound forms — "it's not X, it's Y" / "not just X but Y" — high precision,
    **on by default**;
  - the punchy fragment "X, not Y" — ~45% precision (it fires on legitimate
    contrasts as often as on the rhetorical flourish), so it is **opt-in only**,
    enabled with the special `rhetoric` pattern pack (`--pack rhetoric`).

Patterns report under the `rhetoric` category and contribute a FIXED weight per
match (not per word). A long "it's not about origin, it's about quality" must not
dominate the density score — the value is the highlighted span, not the number.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

_BUNDLED_PATTERNS = Path(__file__).parent / "data" / "patterns-v1.json"

# Special pack name that switches on the opt-in (lower-precision) fragment tier.
RHETORIC_PACK = "rhetoric"

RHETORIC_CATEGORY = "rhetoric"


@dataclass(frozen=True)
class Pattern:
    name: str
    regex: re.Pattern[str]
    category: str
    weight: float
    optin: bool


def load_patterns(*, include_optin: bool = False) -> list[Pattern]:
    """Load bundled regex patterns. Compounds always; opt-in fragment tier only
    when include_optin (the `rhetoric` pack) is requested. Missing file -> []."""
    if not _BUNDLED_PATTERNS.exists():
        return []
    with open(_BUNDLED_PATTERNS, encoding="utf-8") as f:
        data = json.load(f)
    out: list[Pattern] = []
    for p in data.get("patterns", []):
        optin = bool(p.get("optin", False))
        if optin and not include_optin:
            continue
        out.append(
            Pattern(
                name=p["name"],
                regex=re.compile(p["regex"], re.IGNORECASE),
                category=p.get("category", RHETORIC_CATEGORY),
                weight=float(p.get("weight", 1.0)),
                optin=optin,
            )
        )
    return out


def find_pattern_matches(text: str, patterns: list[Pattern]) -> list[dict]:
    """Return raw hits shaped like Lexicon.find_matches(), tagged fixed_weight so
    the scorer counts each construction once rather than per covered word."""
    raw: list[dict] = []
    for pat in patterns:
        for m in pat.regex.finditer(text):
            if m.start() == m.end():
                continue
            raw.append(
                {
                    "start": m.start(),
                    "end": m.end(),
                    "pattern": pat.name,
                    "category": pat.category,
                    "weight": pat.weight,
                    "fixed_weight": True,
                }
            )
    return raw


def patterns_signature(patterns: list[Pattern]) -> list[str]:
    """Stable identifiers for the active patterns, folded into the lexicon hash so
    enabling the fragment tier changes the pinnable version."""
    return sorted(f"{p.name}:{p.weight}:{int(p.optin)}" for p in patterns)
