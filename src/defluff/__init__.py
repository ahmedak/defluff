"""defluff — deterministic AI-slop detector for agent output.

Default path: lexicon-based, instant, zero-model, deterministic.
  import defluff
  r = defluff.detect(text)          # SlopReport
  defluff.score(text)               # float in [0,1]
  defluff.is_slop(text)             # bool (threshold from lexicon data)

Pin a lexicon for reward loops (won't shift if an overlay changes mid-run):
  lex = defluff.load_lexicon()
  best = min(drafts, key=lambda d: defluff.score(d, lexicon=lex))

Curate:
  defluff.lexicon_add("synergy", "corporate")
  defluff.lexicon_ignore("leverage")   # domain jargon
"""

__version__ = "0.1.0"

from .api import (
    Lexicon,
    LexiconNotFoundError,
    PackNotFoundError,
    SlopReport,
    compare,
    detect,
    is_slop,
    lexicon_add,
    lexicon_ignore,
    lexicon_list,
    list_packs,
    load_lexicon,
    score,
    to_human,
    to_json,
)

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
