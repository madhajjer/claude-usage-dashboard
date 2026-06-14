# token-priors.md — the carried-forward core

Beliefs about token cost per task-type. One row = one belief. RECALL reads this; DISTILL
updates exactly one row per pass. Bands are in thousands of tokens (k). Confidence 0..1
rises as a row accumulates ON_BUDGET passes.

| task-type        | pred band (k) | confidence | n | last verdict | note |
|------------------|---------------|------------|---|--------------|------|
| read+answer      | 2 – 6         | 0.30       | 0 | —            | seed guess |
| single-file edit | 4 – 10        | 0.30       | 0 | —            | seed guess |
| multi-file feature | 20 – 60     | 0.20       | 0 | —            | seed guess |
| codebase explore | 15 – 50       | 0.20       | 0 | —            | wide, fan-out |
| backtest/study run | 10 – 40     | 0.20       | 0 | —            | tool-heavy |
| design/doc write | 7 – 14        | 0.55       | 2 | ON_BUDGET    | actual 11.0k non-cache (pass2); +74.9k delta was 90% cache overhead |
| debug loop       | 10 – 40       | 0.15       | 0 | —            | high variance |

Rules:
- After each pass, move the matching band ~30% toward the actual, then set confidence by
  recent ON_BUDGET share.
- A BLIND verdict (>60% off) → add `FLAG` to note; if it repeats, split the row into
  finer task-types (the loop's "informative" move).
