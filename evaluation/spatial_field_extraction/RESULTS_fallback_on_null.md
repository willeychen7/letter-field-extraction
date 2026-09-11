# Would "ask Hunyuan when rules say null" be worth doing?

Read-only analysis over already-scored data (`results/phase9/summary.json`
+ `results/native_benchmark/native_scored.json`). No code changed.

**Question:** for the 4 comparable fields (sender/recipient/total_amount/
due_date), whenever the rules pipeline (`/v1/analyze`) returns `null`
("insufficient evidence"), would substituting Hunyuan's direct-answer
value (`/v1/understand-letter`) as a fallback — never overriding a
confident non-null rules answer — net improve accuracy?

## Method

Of the 196 comparable cells, rules said `null` on **103**. For each of
those 103, look at what the combined-prompt native endpoint said for the
exact same cell and bucket the outcome.

## Result

| outcome | count | % of the 103 |
|---|---:|---:|
| native correct — fallback would have helped | 23 | 22.3% |
| native hallucinated (gold is null, native invented something) | **61** | **59.2%** |
| native also said null — no change | 7 | 6.8% |
| native gave a confident but wrong non-null value | 12 | 11.7% |

**73 of 103 (71%) would get WORSE** — either a fresh hallucination where
the rules were correctly silent, or a confidently wrong answer replacing
an honest "don't know". Only 23 (22%) would actually be recovered.

Examples of each:

```
recovered:   AAA_insurance_Bill  due_date      rules=None -> native='2020-04-08'  (correct)
hurt (hallucination): Water_Bill2 total_amount  rules=None -> native='11 CCF'      (gold is null)
hurt (hallucination): CMS_EOB     due_date      rules=None -> native='XXXXXX'      (gold is null)
hurt (wrong, non-null): Penny_Insurance_Bill recipient  rules=None -> native='John Smith'  (gold='Penny the Pig')
```

## Conclusion

**Net negative as a blanket policy — do not implement.** For every cell a
null-fallback would recover, it damages roughly three others by turning a
safe "insufficient evidence" into a confident wrong answer or a fresh
hallucination. That trade is backwards for this product: a wrong confident
answer is worse than an honest null, and the end user (a non-English-
speaking elder) cannot tell the difference between the 22% that would help
and the 78% that would hurt.

The blocker isn't accuracy on average — it's that Hunyuan doesn't reliably
know when it doesn't know. Until that's solved (out of scope here — would
mean adding a calibrated uncertainty signal, a real model-behavior change,
not a rule), a blanket null-fallback shouldn't be added.
