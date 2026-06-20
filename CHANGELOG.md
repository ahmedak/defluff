# Changelog

All notable changes to defluff — both the package and the bundled **lexicon** —
are recorded here. The lexicon is versioned rather than frozen: see
[Lexicon versioning](README.md#lexicon-versioning) for why the content hash on
every run is the point.

Format loosely follows [Keep a Changelog](https://keepachangelog.com/).
This project adheres to [Semantic Versioning](https://semver.org/).

## [0.1.1] — 2026-06-20

No package or lexicon changes — re-released to fix CI so the package could
actually publish (`v0.1.0`'s tag push never triggered a release).

## [0.1.0] — 2026-06-20

First public release.

### Package

- Deterministic, list-based slop detector: `detect` / `score` / `is_slop` / `compare`.
- CLI: `defluff lint` (exit codes for CI), `defluff score`, `defluff packs`, `defluff lexicon {add,rm,list}`.
- Output leads with the flagged **spans**; the `slop_score` line is a demoted triage signal.
- User + project overlays (`~/.config/defluff/`, `.defluff/`) with atomic, locked writes.
- Bring-your-own lists via `--lexicon` (`.txt`/`.md`/`.json`) and bundled domain `--pack`s.
- MCP server (`defluff-mcp`) exposing `slop_detect` / `slop_add` / `slop_ignore`.
- Pinnable lexicon hash exposed as `SlopReport.lexicon_version` for reproducible CI baselines and reward loops.
- `--category` gating accepts the five curated categories plus `custom` and `rhetoric`.

### Lexicon — `v1`

- 172 curated entries across five weighted categories: `ai-vocab`, `cliche`, `hedge`, `corporate`, `transition`.
- Plus nine opt-in domain packs (corporate-linkedin, startup-vc, marketing-growth, ai-llm, crypto-web3, pr-press-release, academic, wellness-selfhelp, social-media).
- Default gate threshold `0.08`, flagged **provisional** (hand-chosen, not yet corpus-calibrated).

### Rhetoric patterns — `patterns-v1`

- A regex layer alongside the literal lexicon that catches *constructions* with variable slots, beyond fixed phrases. Flagship: the antithesis tell.
- Compound forms (`it's not X, it's Y`, `not just X but Y`) are on by default (high precision); the punchy `X, not Y` fragment is opt-in via `--pack rhetoric` (~50% precision).
- Reported under the `rhetoric` category; each construction counts once toward the score (fixed weight). Enabling the fragment tier changes the pinnable lexicon hash.

[0.1.1]: https://github.com/ahmedak/defluff/releases/tag/v0.1.1
[0.1.0]: https://github.com/ahmedak/defluff/releases/tag/v0.1.0
