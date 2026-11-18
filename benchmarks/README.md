# PDG Fidelity Benchmark

`pdg_groundtruth/<ic>.json` holds hand-labelled ground truth for one datasheet in `testcases/`. Every entry cites a
`page` and a verbatim `evidence` quote.

| Field | Content |
|---|---|
| `pins` | Every pin of one reference package: canonical name, aliases, role, direction |
| `dependencies` | Causal port dependencies (supply → output, input → own output, control/ref/feedback → output) |
| `timing` | Timing / dynamic specs (SR, GBW, settling, propagation delay, ...) |
| `specs` | Spec-table rows with `category` ∈ {ELECTRICAL, ABS_MAX, RECOMMENDED, THERMAL, ESD} |

Run `python run_pdg_benchmark.py` (see the main README). Results are written to
`benchmark_results/pdg_fidelity/<model>/`.

## Metrics
| Metric | Definition |
|---|---|
| Pin P/R | Predicted ports matched to GT pins by name, alias or pin number. NC pins are excluded. |
| Role acc | Role agreement on matched pins. POWER≈GROUND for supply pins, REFERENCE≈FEEDBACK and ENABLE≈CONTROL count as equal. |
| Dep P/R | Directed causal edges of the PDG vs. GT dependencies. Sequencing-only edges from the Eq. 3 precedence rule are excluded. |
| Dep R (datasheet layer) | The same recall, counting only edges whose `origin == "datasheet"`. |
| Sched. order | Share of GT dependencies u→v whose computed schedule satisfies σ(u) < σ(v). |
| Elec. spec recall | Share of GT ELECTRICAL rows matched by a predicted row (symbol or name, plus at least one matching value). |
| Value acc | min/typ/max agreement on matched rows. Unit prefixes (×10³ⁿ) and sign are tolerated. |
| Leak | Share of GT ABS_MAX/RECOMMENDED/THERMAL/ESD rows that the extractor labelled ELECTRICAL, i.e. would be tested. |
| Timing recall | GT timing specs present in the extraction. |
| Provenance score | Ground-truth-free audit: cited page contains the pin name / quote / numbers, DAG validity, datasheet-edge share, datasheet-grounded delays. |

## Known labelling choices
Each file's `notes` field records its labelling choices, for example:
- LM358: the LM358B table was used.
- INA128: P/U grade, CSO SHE.
- TL431: the DBZ package was used.
