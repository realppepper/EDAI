# PDG Fidelity Benchmark — model `deepseek-ai/deepseek-v4.1-flash`

Generated 2026-10-21 15:33. Ground truth: `benchmarks/pdg_groundtruth/` (hand-labelled, page-cited).

| IC | GT score | Pin P/R | Role acc | Dep P/R (full PDG) | Dep R (datasheet layer) | Sched. order | Elec. spec recall | Value acc | Category acc | AbsMax/Rec leak | Timing recall | Provenance score | Pins grounded | Specs grounded | LLM s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| ina128 | **69.5** | 0.88/0.88 | 0.86 | 0.83/0.71 | 0.71 | 1.00 | 0.24 | 0.81 | 1.00 | 0.00 | 0.00 | 81.4 | 100.0% | 100.0% | 32.2 |
| lm317 | **78.4** | 0.75/1.00 | 1.00 | 0.25/0.50 | 0.00 | 0.50 | 1.00 | 0.92 | 1.00 | 0.00 | - | 81.4 | 100.0% | 95.6% | 63.8 |
| lm358 | **95.7** | 1.00/1.00 | 1.00 | 1.00/1.00 | 1.00 | 1.00 | 0.98 | 0.75 | 0.97 | 0.00 | 1.00 | 85.9 | 100.0% | 93.8% | 99.4 |
| lm386 | ERROR: LLM call failed on all models ['deepseek-ai/deepseek-v4.1-fl | | | | | | | | | | | | | | | |
| lm393 | **91.7** | 1.00/1.00 | 1.00 | 1.00/0.75 | 0.75 | 1.00 | 1.00 | 0.76 | 1.00 | 0.00 | 0.50 | 84.2 | 100.0% | 93.8% | 75.4 |
| ne555 | **92.8** | 1.00/1.00 | 0.88 | 1.00/0.54 | 0.54 | 1.00 | 1.00 | 0.91 | 1.00 | 0.00 | 1.00 | 81.0 | 100.0% | 96.0% | 23.9 |
| opa2134 | **68.0** | 0.88/0.88 | 0.57 | 0.00/0.00 | 0.00 | 0.00 | 0.90 | 0.79 | 1.00 | 0.00 | 1.00 | 83.6 | 100.0% | 84.5% | 32.5 |
| tl431 | **77.6** | 0.38/1.00 | 1.00 | 0.50/0.50 | 0.50 | 1.00 | 1.00 | 0.94 | 1.00 | 0.00 | - | 80.0 | 100.0% | 100.0% | 40.8 |

**Mean GT score: 82.0 / 100** over 7 ICs.

Metric definitions: see `benchmarks/README.md`.