# Slop Labeling Rubric

Version: v1 (provisional — pending calibration on labeled set)

## Definition

**Slop** = removable filler that adds no information to the passage.

Explicitly NOT:
- "AI-written" (we do not police authorship)
- "needs editing for other reasons" (grammar, clarity, structure)
- Domain jargon that IS the content (e.g. "leverage" in a finance doc)

## Label values

- `1` = slop: the flagged phrase/span is removable filler; removing it would
  make the prose more direct without losing meaning.
- `0` = not slop: the phrase is doing real work (precision, hedging an
  uncertain claim, domain terminology, stylistic intent).

## Labeling protocol

1. Read the full passage first, then re-read candidate spans.
2. Ask: "If I deleted this phrase and replaced it with nothing (or a single
   word), does the passage lose meaning?" If yes → `0`. If no → `1`.
3. When a hedge phrase hedges a GENUINELY uncertain claim, label `0`. When
   it hedges a confident claim for no reason, label `1`.
4. Phrases that are domain jargon-as-content (e.g. "leverage ratio" in
   banking) label `0` even if they appear in the slop lexicon.
5. Multiple labelers: record your labels independently before comparing.
   Target Cohen's κ ≥ 0.6 on the validation set (deferred to post-v0 full
   protocol).

## Adversarial categories

- **FP trap (jargon-as-content)**: phrases the lexicon flags that are
  legitimate content in the passage's domain. Goal: the detector should NOT
  flag these. Track as false positives.
- **FN trap (novel buzzword)**: empty phrases the lexicon does NOT contain.
  Goal: reveal the lexicon's blind spots. A list-based matcher will miss these
  by design — they bound recall and quantify what a list can and can't catch.

## Calibration vs validation split

- **Calibration set** (~150 passages): self-labeled by the lexicon's author.
  Used to tune category weights and the default threshold. NOT the basis for
  reported precision/recall.
- **Validation set** (adversarial, hand-labeled): labeled by the lexicon's
  author with this rubric, labels frozen BEFORE seeing detector results.
  Reported P/R is on THIS set.
