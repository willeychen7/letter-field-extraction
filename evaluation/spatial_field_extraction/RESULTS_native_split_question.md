# Native direct-answer, split one field per call

Third data point alongside `RESULTS_native_vs_pipeline.md`. Same 50 real
letters, same ground truth, same scoring — this time Hunyuan is asked
**one field per call** (4 separate requests per image: sender, recipient,
amount, due_date) instead of the combined 9-field prompt
`/v1/understand-letter` uses.

This tests an explicit, previously-untested hypothesis already written
into `schemas/mama_helper_v1.py`'s own docstring: *"the split-request
variant... showed better direction accuracy in isolated spot checks but
has NOT been validated on the full ground-truth batch yet."*

Read-only against Phase 3-8; doesn't touch it. Talks to llama-server
(`:8090`) directly with hand-built single-field prompts, using the exact
same template/temperature/model as `/v1/understand-letter` — the ONLY
variable changed is "how many fields per call", so this is a fair,
isolated A/B against the combined-prompt run.

## Result: three ways of answering, same 50 letters

| | rules (`/v1/analyze`) | combined prompt | **split, one field/call** |
|---|---:|---:|---:|
| sender | 79.6% | 44.0% | **62.0%** |
| recipient | 81.6% | 24.0% | **44.0%** |
| total_amount | 89.8% | 50.0% | **38.0%** |
| due_date | 81.6% | 46.0% | **34.0%** |
| **combined** | **83.2%** | **41.0%** | **44.5%** |
| **hallucination rate** | **0.5%** | **31.5%** | **25.0%** |

## The split isn't a uniform win — identity fields improve, value fields get worse

- **sender / recipient improve substantially** (+18pp / +20pp vs the
  combined prompt) — confirms the docstring's hypothesis: asking "who is
  this from / to" in isolation, with no other fields competing for the
  model's attention, measurably helps for this kind of identity judgment.
- **total_amount / due_date get WORSE** (-12pp / -12pp). Not because the
  model reads the numbers wrong more often — inspecting the raw
  responses shows a new failure mode that didn't show up in the combined
  prompt: instead of committing to one value, the model returns a **list
  of candidates**:
  ```
  HOA1   total_amount -> ['360.00', '$0.00', '$360.00']
  HOA3   total_amount -> ['$750.00', '$300.00', '$50.00', ...]
  HOA1   due_date      -> ['1/1/13', '1/31/13']
  ```
  Asked about amount/date with no other context to anchor which one is
  "the" answer, it hedges by listing everything it saw. That's scored as
  wrong here (the schema calls for one value), and it's a legitimate
  instruction-following failure, not a mis-transcription.

## Conclusion

**Splitting the question is a real, measurable improvement over the
combined prompt (41.0% → 44.5% overall, 31.5% → 25.0% hallucination), but
it does not change the standing conclusion.** It is still ~39 points
behind the rules pipeline and hallucinates 50x more often. The improvement
is field-dependent (helps identity fields, hurts value fields), so even a
"smarter prompting" pass over the direct-answer approach doesn't close
the gap — it shifts where the errors are, not how many there are overall.

## Artifacts

- `bench_split_question.py` — the benchmark script (resumable, handles
  the same `.webp` conversion workaround)
- `results/native_split/split_raw.json` — raw per-field responses
- `results/native_split/split_scored.json` — scored rows + summary
