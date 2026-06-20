# Contributing to defluff

## Quickest contribution: expand the lexicon

If you see an AI-filler phrase that defluff misses, add it to `src/defluff/data/lexicon-v1.json`:

```json
{"pattern": "it goes without saying", "category": "hedge", "source": "curated", "added": "YYYY-MM-DD"}
```

Categories:

| Category | Use for |
|----------|---------|
| `ai-vocab` | Words disproportionately overused by LLMs |
| `cliche` | Hollow idioms |
| `hedge` | Empty qualifiers |
| `corporate` | Business buzzwords |
| `transition` | Filler connectives |

Then run `pytest` and open a PR. Include one or two examples of the phrase in the wild (a blog post, a ChatGPT response, etc.) so reviewers can judge false-positive risk.

> The bundled list is JSON so every entry carries a category and (optionally) a weight. That's separate from an end user's *own* list — users point `--lexicon` at a plain `.txt`/`.md` file (one phrase per line) for team-specific phrases. Contributions to the shipped defaults go in the JSON, and should be broadly applicable, not domain- or team-specific.

## Domain packs

Domain-specific phrases (crypto, marketing, academic, …) belong in a **pack** rather than the base list, so users outside that domain don't get false positives. Packs live in `src/defluff/data/packs/<name>.txt` (one phrase per line; `#` comments and `-`/`*` markers allowed). Put high-false-positive terms — words that are often legitimate in the domain — under the commented `# ---` block at the bottom so they're inert until a user opts in. To add a new domain, drop a `.txt` file there and add a row to `src/defluff/data/packs/README.md`; `defluff packs` and `--pack <name>` pick it up automatically.

## Accuracy / eval

`eval/validation.jsonl` is a small hand-labeled set; `python eval/score.py eval/validation.jsonl` reports precision/recall. If you change scoring logic or default weights, run it and note any movement in your PR. Adding labeled examples (especially `FP_trap` jargon-as-content and `FN_trap` novel buzzwords) is a welcome contribution.

## Setup

```bash
git clone https://github.com/ahmedak/defluff
cd defluff
python -m venv .venv && source .venv/bin/activate
pip install -e ".[mcp]"
pip install pytest
pytest
```

## Running tests

```bash
pytest               # all tests
pytest tests/test_smoke.py   # CLI + MCP integration tests
pytest tests/test_lexicon.py # unit tests for the lexicon engine
```

## Code style

- No type: ignore except where unavoidable (circular imports at the boundary)
- No print statements; use `warnings.warn` for non-fatal issues
- Atomic file writes only (`os.replace` pattern — existing code uses this)

## Pull requests

- One concern per PR
- If you're adding a lexicon entry, the PR description should include examples of the phrase used as genuine filler
- If you're changing scoring logic, update `eval/rubric.md` if precision/recall implications change
