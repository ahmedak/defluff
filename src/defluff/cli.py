"""defluff CLI.

Exit codes:
  lint: 0 = at/under threshold (clean), 1 = over (slop), 2 = bad/empty input
  score: 0 always unless bad input (2)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import typer

from . import api
from .lexicon import GATE_CATEGORIES, VALID_CATEGORIES
from .patterns import RHETORIC_PACK
from .report import to_human, to_json


def _split_packs(pack: str | None) -> tuple[list[str] | None, bool]:
    """Parse --pack into (phrase pack names, rhetoric-fragments flag).

    The reserved 'rhetoric' pack name enables the opt-in antithesis fragment
    pattern rather than naming a phrase pack file.
    """
    if not pack:
        return None, False
    names = [p.strip() for p in pack.split(",") if p.strip()]
    rhetoric = RHETORIC_PACK in names
    names = [n for n in names if n != RHETORIC_PACK]
    return (names or None), rhetoric

app = typer.Typer(add_completion=False, help=__doc__)
lexicon_app = typer.Typer(help="Manage the slop lexicon.")
app.add_typer(lexicon_app, name="lexicon")


def _read_input(path: Path | None) -> str:
    if path is not None:
        return path.read_text(encoding="utf-8")
    if sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def _die(msg: str, code: int = 2) -> None:
    typer.echo(f"error: {msg}", err=True)
    raise typer.Exit(code)


@app.command()
def lint(
    file: Path | None = typer.Argument(None, help="Input file; omit to read stdin."),
    json_out: bool = typer.Option(False, "--json", help="Emit machine-readable JSON."),
    threshold: float | None = typer.Option(
        None, "--threshold", "-t",
        help="Slop gate threshold [0,1]. Defaults to value in lexicon data (provisional).",
    ),
    category: str | None = typer.Option(
        None, "--category", "-c",
        help=(
            "Comma-separated list of categories to gate on "
            f"(e.g. 'ai-vocab,hedge'). One of: {', '.join(sorted(GATE_CATEGORIES))}. "
            "Only spans in these categories contribute to the exit-code decision. "
            "Omit to gate on all categories."
        ),
    ),
    lexicon_file: Path | None = typer.Option(
        None, "--lexicon",
        help="Your own phrase list, layered on top of the defaults. "
             "Accepts .txt/.md (one phrase per line) or .json (with categories).",
    ),
    pack: str | None = typer.Option(
        None, "--pack",
        help="Comma-separated bundled domain pack(s) to layer on "
             "(e.g. 'marketing-growth,ai-llm'). Run 'defluff packs' to list them.",
    ),
    no_project_overlay: bool = typer.Option(
        False, "--no-project-overlay",
        help="Disable auto-loading the project .defluff/ overlay (for untrusted CI).",
    ),
):
    """Detect slop in text. Exit 1 if over threshold, 0 if clean, 2 on bad input."""
    raw = _read_input(file)
    if not raw.strip():
        _die("empty input", 2)

    # Validate --category filter
    filter_cats: set[str] | None = None
    if category:
        filter_cats = set()
        for c in category.split(","):
            c = c.strip()
            if c not in GATE_CATEGORIES:
                _die(f"unknown category {c!r}. Valid: {', '.join(sorted(GATE_CATEGORIES))}", 2)
            filter_cats.add(c)

    pack_names, rhetoric_fragments = _split_packs(pack)

    try:
        lex = api.load_lexicon(
            extra_path=lexicon_file,
            packs=pack_names,
            no_project_overlay=no_project_overlay,
            rhetoric_fragments=rhetoric_fragments,
        )
        r = api.detect(raw, lexicon=lex)
    except (api.LexiconNotFoundError, api.PackNotFoundError) as exc:
        _die(str(exc), 2)
        return

    t = threshold if threshold is not None else lex.meta.default_threshold

    if json_out:
        typer.echo(json.dumps(to_json(r), indent=2))
    else:
        typer.echo(to_human(r, threshold=t))

    # When --category is set, recompute the gating score using only filtered spans.
    if filter_cats is not None:
        from .report import MIN_DENOM
        filtered_weight = sum(
            s.weight for s in r.spans if any(c in filter_cats for c in s.categories)
        )
        gating_score = min(1.0, filtered_weight / max(r.n_words, MIN_DENOM))
    else:
        gating_score = r.slop_score

    raise typer.Exit(1 if gating_score > t else 0)


@app.command()
def score(
    file: Path | None = typer.Argument(None, help="Input file; omit to read stdin."),
    pack: str | None = typer.Option(
        None, "--pack", help="Comma-separated bundled domain pack(s) to layer on."
    ),
    no_project_overlay: bool = typer.Option(False, "--no-project-overlay"),
):
    """Print bare slop_score float. Exit 0 (always) unless bad input (exit 2)."""
    raw = _read_input(file)
    if not raw.strip():
        _die("empty input", 2)

    pack_names, rhetoric_fragments = _split_packs(pack)
    try:
        lex = api.load_lexicon(
            packs=pack_names,
            no_project_overlay=no_project_overlay,
            rhetoric_fragments=rhetoric_fragments,
        )
        r = api.detect(raw, lexicon=lex)
    except (api.LexiconNotFoundError, api.PackNotFoundError) as exc:
        _die(str(exc), 2)
        return

    typer.echo(str(r.slop_score))
    raise typer.Exit(0)


@app.command()
def packs():
    """List the bundled domain packs (use with 'defluff lint --pack NAME')."""
    names = api.list_packs()
    if not names:
        typer.echo("no packs bundled")
    else:
        for name in names:
            typer.echo(name)
    # Pattern packs aren't phrase files; surface the reserved one explicitly.
    typer.echo(f"{RHETORIC_PACK}  (pattern pack: opt-in 'X, not Y' antithesis fragment)")


# ---------------------------------------------------------------------------
# lexicon sub-commands
# ---------------------------------------------------------------------------

@lexicon_app.command("add")
def lexicon_add_cmd(
    pattern: str = typer.Argument(..., help="Phrase to add."),
    category: str = typer.Option(..., "--category", "-c", help=f"One of: {', '.join(sorted(VALID_CATEGORIES))}"),
    scope: str = typer.Option("user", "--scope", "-s", help="'user' or 'project'"),
    weight: float | None = typer.Option(None, "--weight", help="Override category default weight."),
):
    """Add a phrase to the slop lexicon."""
    try:
        result = api.lexicon_add(pattern, category, scope=scope, weight=weight)
        typer.echo(f"added [{result['category']}] {result['added']!r}  (scope: {result['scope']})")
    except (ValueError, OSError) as exc:
        _die(str(exc))


@lexicon_app.command("rm")
def lexicon_rm_cmd(
    pattern: str = typer.Argument(..., help="Phrase to suppress."),
    scope: str = typer.Option("user", "--scope", "-s", help="'user' or 'project'"),
):
    """Mark a phrase as NOT slop (add to ignore list)."""
    try:
        result = api.lexicon_ignore(pattern, scope=scope)
        typer.echo(f"ignored {result['ignored']!r}  (scope: {result['scope']})")
    except (ValueError, OSError) as exc:
        _die(str(exc))


@lexicon_app.command("list")
def lexicon_list_cmd(
    scope: str | None = typer.Option(None, "--scope", "-s"),
    category: str | None = typer.Option(None, "--category", "-c"),
    json_out: bool = typer.Option(False, "--json"),
):
    """List active lexicon entries."""
    entries = api.lexicon_list(scope=scope)
    if category:
        entries = [e for e in entries if e["category"] == category]
    if json_out:
        typer.echo(json.dumps(entries, indent=2))
    else:
        for e in sorted(entries, key=lambda x: (x["category"], x["pattern"])):
            w = f"  weight={e['weight']}" if e["weight"] is not None else ""
            typer.echo(f"  [{e['category']}] {e['pattern']!r}  (source: {e['source']}){w}")
        typer.echo(f"\n{len(entries)} entries")


if __name__ == "__main__":
    app()
