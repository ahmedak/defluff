"""defluff MCP server.

Exposes three tools so any MCP-aware agent auto-discovers slop detection
and curation without bespoke wiring:
  slop_detect(text)          -> SlopReport JSON
  slop_add(pattern, category, scope?) -> AddResult JSON
  slop_ignore(pattern, scope?)        -> AddResult JSON

The server holds one Lexicon handle and invalidates it after slop_add /
slop_ignore so the next slop_detect call sees the write, even within the
same long-lived process.

Run: defluff-mcp  (entry point registered in pyproject.toml)
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from . import api
from .report import to_json

mcp = FastMCP("defluff")

# Process-level handle — rebuilt on first call or after a write.
_lexicon: api.Lexicon | None = None


def _get_lex() -> api.Lexicon:
    global _lexicon
    if _lexicon is None:
        _lexicon = api.load_lexicon()
    return _lexicon


def _invalidate() -> None:
    global _lexicon
    _lexicon = None


@mcp.tool()
def slop_detect(text: str) -> dict:
    """Detect AI-slop (clichés, hedges, filler, AI-vocab) in text.

    Returns slop_score 0-1 + exact slop spans. Deterministic, local, no LLM.
    Use before returning generated prose to self-check, or to gate/rank drafts.
    """
    if not text or not text.strip():
        return {"error": "text must not be empty"}
    try:
        r = api.detect(text, lexicon=_get_lex())
        return to_json(r)
    except api.LexiconNotFoundError as exc:
        return {"error": str(exc)}
    except Exception as exc:
        return {"error": f"detection failed: {exc}"}


@mcp.tool()
def slop_add(
    pattern: str,
    category: str,
    scope: str = "project",
) -> dict:
    """Add a phrase to the slop lexicon so future detections flag it.

    Use when the user says something is slop / a banned phrase.
    scope='project' (this repo, shared via git) or 'user' (machine-wide).
    """
    try:
        result = api.lexicon_add(pattern, category, scope=scope)
        _invalidate()
        return result
    except ValueError as exc:
        return {"error": str(exc)}
    except OSError as exc:
        return {"error": f"could not write overlay: {exc}"}


@mcp.tool()
def slop_ignore(pattern: str, scope: str = "project") -> dict:
    """Mark a phrase as NOT slop (e.g. domain jargon) so it stops being flagged.

    Use when the user says a flagged phrase is actually fine in this context.
    scope='project' (this repo) or 'user' (machine-wide).
    """
    try:
        result = api.lexicon_ignore(pattern, scope=scope)
        _invalidate()
        return result
    except ValueError as exc:
        return {"error": str(exc)}
    except OSError as exc:
        return {"error": f"could not write ignore file: {exc}"}


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
