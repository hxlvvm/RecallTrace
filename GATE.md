# Day-3 gate (written 2026-10-07, before any parser or model was run on the test split)

Test data: `data/gold/scope_probes.jsonl`, 150 hand-written probes over 58 recall records from the
held-out test split (`data/split.json`, split by recall event). Each probe is one device unit and the
expected verdict: `affected`, `not_affected` or `unresolved` (the unit lacks what the scope needs).

## Scope check (does this recall cover this unit?)

| metric | pass if |
|---|---|
| wrong definitive verdicts (affected <-> not_affected) | <= 5 % of probes |
| false reassurance (truth affected, system says not_affected) | <= 2 probes |
| coverage: definitive verdicts on probes whose truth is definitive | >= 80 % |
| definitive verdicts on the 13 `unresolved` probes | <= 1 |

## Identity retrieval (which recall record is this inventory row?)

Synthetic inventory rows derived from test-split records, with typed noise (manufacturer aliases,
abbreviated model names, typos, missing identifiers) and a hand-written hard slice.

| metric | pass if |
|---|---|
| top-3 recall on rows that belong to a recalled product | >= 90 % |
| gain over the exact-ID + fuzzy baseline on the noisy subset | >= 10 points top-3 recall, or >= 20 % fewer candidates at equal recall |

## Decision rule

- LLM-assisted extraction must beat the regex-only parser on the scope probes (fewer wrong
  verdicts at equal or better coverage). If it does not, the regex parser ships and the README says so.
- If the learned reranker does not beat the baseline, the baseline ships and the README says so.
- If grounded extraction fails the scope thresholds, the project stops here and the result is
  written up as is.
