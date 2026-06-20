"""Strip code fences, URLs, and markdown markup before lexicon matching."""

from __future__ import annotations

import re

_CODE_FENCE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE = re.compile(r"`[^`]*`")
_URL = re.compile(r"https?://\S+|www\.\S+")
_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_MD_QUOTE = re.compile(r"^>\s?", re.MULTILINE)
_MD_EMPH = re.compile(r"[*_~]{1,3}")
_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")  # [text](url) -> text


def clean(text: str) -> str:
    """Remove code/URLs/markdown markup before lexicon matching."""
    text = _CODE_FENCE.sub(" ", text)
    text = _INLINE_CODE.sub(" ", text)
    text = _MD_LINK.sub(r"\1", text)
    text = _URL.sub(" ", text)
    text = _MD_HEADING.sub("", text)
    text = _MD_QUOTE.sub("", text)
    text = _MD_EMPH.sub("", text)
    return text
