# Research notes

## Research question

What types of context actually improve NL2SQL reliability, and where does additional context stop
helping or start hurting?

## Hypothesis (to be tested, not assumed)

Reliable NL2SQL depends more on business semantics (identity, metric definitions, domain rules)
than on schema detail. The experiments are designed so the opposite results are also visible:
- schema is enough
- returns diminish
- more context hurts (dilution)
- some context helps one question type and hurts another

## Dataset

Olist Brazilian E-Commerce (CC BY-NC-SA 4.0), loaded into a normalised PostgreSQL schema.
See `data/README.md` and `data/reports/data_quality.md`.

## Benchmark design

Pilot: 26 questions in `benchmark/pilot.yaml` (version `pilot-2`). It is a **development set**: the semantic layer and
the benchmark were adjusted using pilot runs, so it can't serve as a held-out test.

| Category | Questions |
|---|---:|
| schema | 6 |
| relational | 8 |
| metric | 5 |
| trap | 4 |
| ambiguous | 3 |

- Each question has trusted SQL whose *result* is the ground truth, plus the tables it requires.
- Each question also has `required_knowledge` (the minimal sufficient knowledge items) and `related_knowledge` (relevant but redundant items).
- Includes **control** questions (answerable from schema alone) and **anti-trap** questions (p03, p17), where a semantic rule must *not* be applied.
- Ambiguous questions have one "organisation" interpretation (the one in the semantic layer) plus documented reasonable alternatives.

## Experimental variables

- **Independent:** context level (E0–E6); context mode (retrieved vs gold).
- **Held constant, and recorded in every run manifest:**
  - model; requested and effective temperature
  - prompt template and hash
  - embedding model; top-k per type (3)
  - semantic-layer hash; benchmark version and hash
  - database fingerprint; PostgreSQL version
  - number of repeats

## Experimental configurations

The Context Ladder (see README). Gold conditions E4–E6 replace retrieval with each question's required knowledge,
which separates the value of the knowledge from the quality of retrieval.

## Evaluation metrics

- **Primary:** result correctness, as the mean over repeats. See `evaluation/compare_results.py` for the scalar, set, ordered (tie-tolerant), tolerance and NULL rules.
- **Secondary:**
  - "plausible" correctness, which also accepts alternative interpretations
  - range of accuracy across repeats, and the number of unstable questions
  - execution success; SQL validity
  - input, output and reasoning tokens; latency
  - retrieval recall (required items) and precision (required + related items)
  - rule-based failure category, with manual overrides

## Potential confounders

- **Prompt length grows with level.** Gains may come from the kind of context or from its amount. The planned context-quantity experiment addresses this.
- **Pretraining contamination.** The pilot model writes exact Olist table and column names with no schema at all (51% at E0), so E0 largely measures memory of a public dataset.
- **Authoring bias.** The same author wrote the semantic layer and the benchmark. E5 reaching 100% in every repeat is consistent with "the definitions contain the answers". A held-out benchmark written independently of the semantic layer is needed.
- **Model non-determinism.** The pilot model only runs at its default temperature, so each condition is repeated 3 times.
- **Small n.** 26 questions, with 3–8 per category. Pilot differences are directional only.

## Results

*Populated only from actual runs.*

- **2026-10-05 pilot**, run `20261005T145111Z`: 26 questions × 10 conditions × 3 repeats, model `openai.gpt-6-sol`.
  Mean result accuracy:

  | Context | E0 | E1 | E2 | E3 | E4 | E5 | E6 |
  |---|---:|---:|---:|---:|---:|---:|---:|
  | Retrieved | 51% | 63% | 64% | 67% | 65% | 100% | 100% |
  | Gold | | | | | 65% | 97% | 100% |

  Details, prompts, retrieval examples and failures are in [pilot-review.md](pilot-review.md).

## Failure analysis

See [pilot-review.md § 6](pilot-review.md#6-interesting-failures), failures F1–F7.

## Observations

- Structure stops being the bottleneck at E1. Relational questions are solved even at E0, for this model and dataset.
- The improvement comes from metric definitions (E4 → E5: 9 questions fixed, none broken).
- Entity definitions and domain rules added nothing *once metric definitions were self-contained*. In an earlier
  pilot run, domain rules seemed to help only because metrics referred to a term defined in a rule.
- Relevant context reduced output and reasoning tokens and latency, even though the prompt grew 24×.
- No regressions were observed at any step of the ladder.

## Open questions

- Does business context still help on questions the semantic layer was not written for?
- Does the model follow *misleading* definitions as faithfully as correct ones? (Experiment C)
- Would a model with less prior knowledge of Olist show a different ladder shape?
- Flat, self-contained knowledge items vs items linked by dependencies: which is easier to maintain, and which retrieves better?
