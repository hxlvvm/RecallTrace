# Day-3 gate result (2026-10-07)

Thresholds are in `GATE.md`, committed before anything was run on the test split.

## Scope check

Development probes (`scope_probes.jsonl`, 150 probes, 58 records) were used while fixing bugs, so
they are optimistic. The blind probes (`scope_probes_blind.jsonl`, 70 probes, 30 further test
records) were written after both parsers were frozen. Blind results are as measured at the freeze.

| parser | set | correct | wrong definitive | false reassurance | coverage | definitive on unresolved | gate |
|---|---|---|---|---|---|---|---|
| regex only | dev probes | 141/150 | 7 | 2 | 1.000 | 2 | fail |
| LLM + checks | dev probes | 142/150 | 1 | 0 | 0.956 | 1 | pass |
| regex only | **blind** | 61/70 | 5 | 2 | 0.983 | 3 | fail |
| LLM + checks | **blind** | **64/70** | **2** | **1** | 0.950 | **1** | **pass** |

The one blind false reassurance was a software wildcard (`6.XX`) that the version matcher compared
literally. It was fixed afterwards. The blind numbers above stay as measured before that fix.

## Identity retrieval

Synthetic rows from all 543 test-split records, five noise types each. "Filtered" top-3 means
other recalls of the same product do not count against the rank.

| row type | baseline top-3 | logistic reranker top-3 |
|---|---|---|
| clean | 0.937 | 0.945 |
| brand alias (with LLM firm aliases) | 0.913 | 0.945 |
| typo | 0.910 | 0.915 |
| no model number | 0.703 | 0.735 |
| two-word name, no model number | 0.499 | 0.532 |
| all | 0.793 | 0.814 |

**The 90 % target is missed. The reranker adds 2.6 points on the noisy rows, against the 10 points
required.**

## Decision

- **The scope gate passes**, so the project continues. LLM-assisted extraction ships.
- **The identity gate fails** on rows without a model number. Such a row is genuinely ambiguous across
  repeat recalls of a product family. The application therefore reports it as "possible recalls,
  model number needed" rather than as a match.
- **The reranker did not reach its margin**, so the hand-weighted baseline ships. The reranker stays
  in the evaluation as an ablation.
