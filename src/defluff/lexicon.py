"""Lexicon loading, resolution, and matching.

Resolution order (later wins; ignore always wins):
  1. bundled defaults   src/defluff/data/lexicon-<ver>.json
  2. user overlay       ~/.config/defluff/lexicon.json
  3. project overlay    ./.defluff/lexicon.json (walk up to git root)
  4. call-time          load_lexicon(extra_path=...)
  minus ignore overlays at user + project scope

Walk-up stops at the first .git/ or .defluff/ found (whichever is nearer).
Disable project overlay: DEFLUFF_NO_PROJECT_OVERLAY=1 or --no-project-overlay.

Writes are atomic (tmp + os.replace) and cross-process locked (.lock sidecar).
Reads tolerate a corrupt overlay: warn to stderr, skip it, never crash detect().
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import warnings
from dataclasses import dataclass, field
from pathlib import Path

import ahocorasick
import filelock

from . import patterns as _patterns

# ---------------------------------------------------------------------------
# Constants / paths
# ---------------------------------------------------------------------------

_BUNDLED_LEXICON = Path(__file__).parent / "data" / "lexicon-v1.json"
_PACKS_DIR = Path(__file__).parent / "data" / "packs"
_USER_CONFIG_DIR = Path.home() / ".config" / "defluff"
_USER_LEXICON = _USER_CONFIG_DIR / "lexicon.json"
_USER_IGNORE = _USER_CONFIG_DIR / "ignore.json"

# Categories a user may `lexicon add` a literal phrase to (the curated five).
VALID_CATEGORIES = {"cliche", "hedge", "ai-vocab", "corporate", "transition"}

# Categories that can appear in output and so be gated on via --category. Adds
# the file-only `custom` bucket and the regex-only `rhetoric` layer, neither of
# which accepts `lexicon add`.
GATE_CATEGORIES = VALID_CATEGORIES | {"custom", "rhetoric"}


# ---------------------------------------------------------------------------
# Bundled domain packs
# ---------------------------------------------------------------------------

class PackNotFoundError(ValueError):
    """Raised when --pack names a pack that isn't bundled."""


def list_packs() -> list[str]:
    """Return the names of bundled domain packs (filename stems), sorted."""
    if not _PACKS_DIR.is_dir():
        return []
    return sorted(p.stem for p in _PACKS_DIR.glob("*.txt"))


def pack_path(name: str) -> Path:
    """Resolve a bundled pack name to its file path, or raise PackNotFoundError."""
    candidate = _PACKS_DIR / f"{name}.txt"
    if not candidate.is_file():
        available = ", ".join(list_packs()) or "(none bundled)"
        raise PackNotFoundError(f"unknown pack {name!r}. Available: {available}")
    return candidate


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------

class LexiconNotFoundError(FileNotFoundError):
    """Raised when the bundled lexicon data file is missing."""


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class Entry:
    pattern: str           # normalized (lowercase, stripped)
    category: str
    source: str = "user"
    weight: float | None = None  # None = use category default


@dataclass
class LexiconMeta:
    version: str
    default_threshold: float
    threshold_provisional: bool
    category_weights: dict[str, float]


@dataclass
class Lexicon:
    """Resolved, built, immutable lexicon. Pass to detect/score/is_slop to pin."""
    meta: LexiconMeta
    entries: list[Entry]
    ignore_patterns: frozenset[str]
    version: str           # hash of resolved entry set
    _automaton: ahocorasick.Automaton = field(repr=False, compare=False)
    patterns: list[_patterns.Pattern] = field(
        default_factory=list, repr=False, compare=False
    )

    # ------------------------------------------------------------------
    # Internal matching
    # ------------------------------------------------------------------

    def find_matches(self, text: str) -> list[dict]:
        """Return raw Aho-Corasick hits with word-boundary validation."""
        text_lower = text.lower()
        raw: list[dict] = []
        for end_idx, entry in self._automaton.iter(text_lower):
            pat = entry.pattern
            start_idx = end_idx - len(pat) + 1
            # Whole-token boundary check: char before start must be non-word
            # and char after end must be non-word (or at string edge).
            if start_idx > 0 and text_lower[start_idx - 1].isalnum():
                continue
            after = end_idx + 1
            if after < len(text_lower) and text_lower[after].isalnum():
                continue
            raw.append({
                "start": start_idx,
                "end": end_idx + 1,
                "pattern": pat,
                "category": entry.category,
                "weight": entry.weight,
            })
        return raw


# ---------------------------------------------------------------------------
# Lexicon file I/O (atomic writes, locked, corrupt-tolerant reads)
# ---------------------------------------------------------------------------

def _lock_path(p: Path) -> Path:
    return p.with_suffix(p.suffix + ".lock")


# Markdown/plain-text list markers ("- ", "* ", "1. ") stripped per line.
_LIST_MARKER_RE = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+")

# Plain-text entries carry no category, so they land in a neutral 'custom'
# bucket (weight 1.0) rather than being mislabeled as one of the curated five.
_PLAINTEXT_DEFAULT_CATEGORY = "custom"


def _read_overlay(path: Path) -> list[dict]:
    """Read an overlay file. JSON (list of dicts) or plain-text/markdown
    (one phrase per line). Returns [] on missing or corrupt file.

    Plain text (.txt / .md): one phrase per line, blank lines and lines
    starting with '#' ignored, leading list markers ('-', '*', '1.') stripped.
    Every entry lands in the neutral 'custom' category (weight 1.0) — use
    JSON to set per-phrase categories or weights.
    """
    if not path.exists():
        return []
    if path.suffix.lower() in {".txt", ".md"}:
        return _read_plaintext_overlay(path)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        warnings.warn(
            f"defluff: skipping corrupt overlay {path}: {exc}",
            stacklevel=4,
        )
        return []


def _read_plaintext_overlay(path: Path) -> list[dict]:
    """Parse a .txt/.md phrase list into overlay entries."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        warnings.warn(f"defluff: skipping unreadable overlay {path}: {exc}", stacklevel=5)
        return []
    entries: list[dict] = []
    for line in text.splitlines():
        phrase = _LIST_MARKER_RE.sub("", line.strip()).strip()
        if not phrase or phrase.startswith("#"):
            continue
        entries.append({
            "pattern": phrase,
            "category": _PLAINTEXT_DEFAULT_CATEGORY,
            "source": "user",
        })
    return entries


def _read_ignore(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as exc:
        warnings.warn(f"defluff: skipping corrupt ignore file {path}: {exc}", stacklevel=4)
        return []


def _write_overlay(path: Path, entries: list[dict]) -> None:
    """Atomic write: tmp file + os.replace, protected by a .lock sidecar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = filelock.FileLock(_lock_path(path), timeout=5)
    with lock:
        # Re-read inside lock so we don't clobber concurrent writes.
        existing = _read_overlay(path)
        # Merge: dedup by normalized pattern (new entry wins on conflict).
        by_pattern: dict[str, dict] = {_norm(e["pattern"]): e for e in existing}
        for entry in entries:
            by_pattern[_norm(entry["pattern"])] = entry
        merged = list(by_pattern.values())
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)


def _write_ignore(path: Path, patterns: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock = filelock.FileLock(_lock_path(path), timeout=5)
    with lock:
        existing = set(_read_ignore(path))
        existing.update(_norm(p) for p in patterns)
        merged = sorted(existing)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(merged, f, indent=2, ensure_ascii=False)
        os.replace(tmp, path)


# ---------------------------------------------------------------------------
# Path discovery (walk-up bounded at git root or first .defluff/)
# ---------------------------------------------------------------------------

def _find_project_defluff(start: Path) -> Path | None:
    """Walk up from start, stop at .git or .defluff. Return .defluff/ dir or None."""
    if os.environ.get("DEFLUFF_NO_PROJECT_OVERLAY"):
        return None
    current = start.resolve()
    while True:
        candidate = current / ".defluff"
        if candidate.is_dir():
            return candidate
        if (current / ".git").exists():
            # Reached the git root without finding a .defluff above it.
            return None
        parent = current.parent
        if parent == current:
            return None
        current = parent


def _project_lexicon_path() -> Path | None:
    defluff_dir = _find_project_defluff(Path.cwd())
    return (defluff_dir / "lexicon.json") if defluff_dir else None


def _project_ignore_path() -> Path | None:
    defluff_dir = _find_project_defluff(Path.cwd())
    return (defluff_dir / "ignore.json") if defluff_dir else None


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def _norm(pattern: str) -> str:
    return pattern.strip().lower()


# ---------------------------------------------------------------------------
# Resolution: load + merge all layers into a Lexicon
# ---------------------------------------------------------------------------

def _load_bundled() -> tuple[LexiconMeta, list[Entry]]:
    if not _BUNDLED_LEXICON.exists():
        raise LexiconNotFoundError(
            f"defluff: bundled lexicon not found at {_BUNDLED_LEXICON}. "
            "Re-install the package: pip install --force-reinstall defluff"
        )
    with open(_BUNDLED_LEXICON, encoding="utf-8") as f:
        data = json.load(f)
    meta = LexiconMeta(
        version=data["version"],
        default_threshold=data["default_threshold"],
        threshold_provisional=data["threshold_provisional"],
        category_weights=data["category_weights"],
    )
    entries = [
        Entry(
            pattern=_norm(e["pattern"]),
            category=e["category"],
            source=e.get("source", "curated"),
            weight=e.get("weight"),  # honor per-entry weight overrides
        )
        for e in data["entries"]
    ]
    return meta, entries


def _build_automaton(entries: list[Entry]) -> ahocorasick.Automaton:
    A = ahocorasick.Automaton()
    for entry in entries:
        A.add_word(entry.pattern, entry)
    if entries:
        A.make_automaton()
    return A


def _hash_entries(
    entries: list[Entry],
    ignore: frozenset[str],
    pattern_sig: list[str] | None = None,
) -> str:
    key = json.dumps(
        [(e.pattern, e.category, e.weight) for e in sorted(entries, key=lambda e: e.pattern)]
        + sorted(ignore)
        + (pattern_sig or []),
        sort_keys=True,
    )
    return hashlib.sha256(key.encode()).hexdigest()[:12]


def load_lexicon(
    *,
    extra_path: Path | None = None,
    packs: list[str] | None = None,
    no_project_overlay: bool = False,
    rhetoric_fragments: bool = False,
) -> Lexicon:
    """Resolve all overlay layers and build a Lexicon handle.

    `packs` names bundled domain packs (see list_packs()) to layer on top of
    the defaults. `rhetoric_fragments` enables the opt-in, lower-precision
    "X, not Y" fragment pattern (the high-precision compound antithesis patterns
    are always on). Pass the returned handle to detect/score/is_slop to pin the
    lexicon for reward loops. The convenience auto-load in those functions uses
    an mtime-keyed cache so the automaton is rebuilt only when a file changes.
    """
    meta, bundled = _load_bundled()

    # Collect overlay entries: later scope wins on dedup.
    by_pattern: dict[str, Entry] = {e.pattern: e for e in bundled}

    use_project = not no_project_overlay and not os.environ.get("DEFLUFF_NO_PROJECT_OVERLAY")

    # Overlays in resolution order — later wins.
    overlay_paths: list[Path | None] = [_USER_LEXICON]
    if use_project:
        overlay_paths.append(_project_lexicon_path())
    for name in packs or []:
        overlay_paths.append(pack_path(name))
    overlay_paths.append(extra_path)

    for path in overlay_paths:
        if path is None:
            continue
        for raw in _read_overlay(path):
            p = _norm(raw.get("pattern", ""))
            if p:
                by_pattern[p] = Entry(
                    pattern=p,
                    category=raw.get("category", "cliche"),
                    source=raw.get("source", "user"),
                    weight=raw.get("weight"),
                )

    # Ignore lists: user + project
    ignore_norms: set[str] = set()
    ignore_paths: list[Path | None] = [_USER_IGNORE]
    if use_project:
        ignore_paths.append(_project_ignore_path())
    for path in ignore_paths:
        if path is None:
            continue
        for pat in _read_ignore(path):
            ignore_norms.add(_norm(pat))

    # Apply ignores
    for p in list(ignore_norms):
        by_pattern.pop(p, None)

    entries = list(by_pattern.values())
    ignore_frozen = frozenset(ignore_norms)

    # Structural regex patterns (rhetoric layer): compounds always, opt-in
    # fragment only when requested. Folded into the version hash so toggling it
    # changes the pinnable lexicon id.
    resolved_patterns = _patterns.load_patterns(include_optin=rhetoric_fragments)
    pattern_sig = _patterns.patterns_signature(resolved_patterns)

    version_hash = _hash_entries(entries, ignore_frozen, pattern_sig)
    automaton = _build_automaton(entries)

    return Lexicon(
        meta=meta,
        entries=entries,
        ignore_patterns=ignore_frozen,
        version=version_hash,
        _automaton=automaton,
        patterns=resolved_patterns,
    )


# ---------------------------------------------------------------------------
# mtime-keyed process-level cache (auto-load used by detect/score/is_slop)
# ---------------------------------------------------------------------------

_cache: dict[tuple, Lexicon] = {}


def _mtime(p: Path) -> float:
    try:
        return p.stat().st_mtime
    except OSError:
        return 0.0


def _cache_key() -> tuple:
    proj_lex = _project_lexicon_path()
    proj_ign = _project_ignore_path()
    return (
        _mtime(_BUNDLED_LEXICON),
        _mtime(_USER_LEXICON),
        _mtime(_USER_IGNORE),
        _mtime(proj_lex) if proj_lex else 0.0,
        _mtime(proj_ign) if proj_ign else 0.0,
        os.environ.get("DEFLUFF_NO_PROJECT_OVERLAY", ""),
    )


def get_default_lexicon() -> Lexicon:
    """Return the cached Lexicon for the current overlay state, rebuilding on change."""
    key = _cache_key()
    if key not in _cache:
        _cache.clear()  # only keep one entry; key encodes all relevant state
        _cache[key] = load_lexicon()
    return _cache[key]


def _invalidate_cache() -> None:
    _cache.clear()


# ---------------------------------------------------------------------------
# Write surfaces: lexicon_add / lexicon_ignore
# ---------------------------------------------------------------------------

def _scope_paths(scope: str) -> tuple[Path, Path]:
    """Return (lexicon_path, ignore_path) for a given scope."""
    if scope == "user":
        return _USER_LEXICON, _USER_IGNORE
    if scope == "project":
        defluff_dir = _find_project_defluff(Path.cwd())
        if defluff_dir is None:
            # Create .defluff/ in cwd if no git root found — best-effort.
            defluff_dir = Path.cwd() / ".defluff"
            defluff_dir.mkdir(exist_ok=True)
        return defluff_dir / "lexicon.json", defluff_dir / "ignore.json"
    raise ValueError(f"scope must be 'user' or 'project', got {scope!r}")


def lexicon_add(
    pattern: str,
    category: str,
    *,
    scope: str = "user",
    weight: float | None = None,
) -> dict:
    """Add a pattern to the slop lexicon. Idempotent (dedup by normalized pattern).

    Returns {"added": pattern, "scope": scope, "category": category}.
    """
    if category not in VALID_CATEGORIES:
        raise ValueError(f"category must be one of {sorted(VALID_CATEGORIES)}")
    norm = _norm(pattern)
    if not norm:
        raise ValueError("pattern must not be empty")
    lex_path, _ = _scope_paths(scope)
    entry: dict = {"pattern": norm, "category": category, "source": "user", "added": _today()}
    if weight is not None:
        entry["weight"] = weight
    _write_overlay(lex_path, [entry])
    _invalidate_cache()
    return {"added": norm, "scope": scope, "category": category}


def lexicon_ignore(pattern: str, *, scope: str = "user") -> dict:
    """Mark a pattern as NOT slop in the given scope.

    Returns {"ignored": pattern, "scope": scope}.
    """
    norm = _norm(pattern)
    if not norm:
        raise ValueError("pattern must not be empty")
    _, ign_path = _scope_paths(scope)
    _write_ignore(ign_path, [norm])
    _invalidate_cache()
    return {"ignored": norm, "scope": scope}


def lexicon_list(*, scope: str | None = None) -> list[dict]:
    """Return current entries visible to detect(), optionally filtered by scope."""
    lex = get_default_lexicon()
    entries = [
        {"pattern": e.pattern, "category": e.category, "source": e.source, "weight": e.weight}
        for e in lex.entries
    ]
    if scope:
        entries = [e for e in entries if e["source"] == scope]
    return entries


def _today() -> str:
    from datetime import date
    return date.today().isoformat()
