# defluff domain packs

Opt-in phrase lists for specific kinds of writing. Each layers on top of the
built-in lexicon, so you get the defaults **plus** the domain's buzzwords. These
ship inside the package — load them by name, no path needed:

```bash
defluff packs                              # list available packs
defluff lint post.md --pack marketing-growth
defluff lint post.md --pack marketing-growth,ai-llm   # stack several
```

You can stack your own list too — point `--lexicon` at any `.txt`/`.md`
(one phrase per line). Pack entries report under the `custom` category.

| Pack | What it catches | Phrases |
|------|-----------------|--------:|
| [`corporate-linkedin.txt`](corporate-linkedin.txt) | Office/LinkedIn jargon — *circle back, boil the ocean, double-click on* | 31 |
| [`startup-vc.txt`](startup-vc.txt) | Pitch-deck speak — *disruptive, moat, hockey stick, secret sauce* | 24 |
| [`marketing-growth.txt`](marketing-growth.txt) | Hype copy — *best-of-breed, frictionless, supercharge, turnkey* | 30 |
| [`ai-llm.txt`](ai-llm.txt) | LLM tells — *testament to, a beacon of, navigating the complexities* | 31 |
| [`social-media.txt`](social-media.txt) | X/Twitter engagement-bait — *let that sink in, hot take, a thread* | 27 |
| [`crypto-web3.txt`](crypto-web3.txt) | Crypto hype — *to the moon, wagmi, trustless, bank the unbanked* | 33 |
| [`pr-press-release.txt`](pr-press-release.txt) | Press-release boilerplate — *thrilled to announce, industry-leading* | 27 |
| [`academic.txt`](academic.txt) | Research filler/hedging — *it is well known that, more research is needed* | 30 |
| [`wellness-selfhelp.txt`](wellness-selfhelp.txt) | Influencer-speak — *trust the process, do the work, raise your vibration* | 31 |

## High false-positive terms ship parked (disabled by default)

Some phrases are real words in their own domain (`pivot`, `runway`, `detox`,
`decentralized`). Those sit at the bottom of each pack as commented-out lines —
`defluff` ignores `#` lines, so they do nothing until you opt in by removing the
leading `# `.

## A note on the social-media pack

Many of those phrases are used *deliberately* to boost engagement. The pack is
for writers who want to strip engagement-bait — not a claim that the phrases are
always wrong.

## Sources & accuracy

Phrases were compiled from public buzzword lists, style guides, and glossaries
(linked in the PR that added each pack). They're curated rather than measured — treat a
pack as a strong starting point you prune with `defluff lexicon rm`, never as a
verdict. Found a miss or a bad entry? PRs welcome — see [CONTRIBUTING](../../../../CONTRIBUTING.md).
