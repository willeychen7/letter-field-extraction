# Phase 6 — Low-Confidence Domain Resolution (analysis)

Analysis only. Phase 3 / Phase 4 (7-class) / Phase 5 all stay frozen.
No Amount/DueDate/PaymentStatus/Action change. No semantic similarity.
No per-image rules. The question is *why* low-gap domain classification
is unreliable, and whether one **general** method can lift it without
denting the 97 % high-confidence accuracy.

## What high-confidence looks like (the baseline to protect)

29 of 30 gap ≥ 3 cases are correct. Their evidence profile:

| issuer | subject groups | layout | count |
|---|---|---|---|
| ✅ | 2 | ✅ | 11 |
| ✅ | 1 | ✅ | 7 |
| ✅ | 3 | ✅ | 7 |
| ✅ | 1–2 | ✗ | 4 |

**Every confident-correct case has an issuer match.** Confident = a real
institution word in the letterhead + at least one corroborating
structure signal. The issuer group is load-bearing.

## Why low-gap cases go wrong — four distinct mechanisms

### M1. Substring false-match inflates a competitor's issuer/subject

Confirmed by grep:

| doc | phantom hit | reality |
|---|---|---|
| `DMV_Notice` | `vision` ⊂ **di**`vision` (of Motor Vehicles) → HEALTHCARE issuer +2.0 | HEALTHCARE score 3.0 vs GOVERNMENT 4.0 → gap **1.0** |
| `DMV_Notice` | `procedure` ⊂ `procedures`, `na ` ⊂ … | more phantom HEALTHCARE |
| `Eye_care-invoice` | `vin` ⊂ arbitrary word → INSURANCE subject group | INSURANCE reaches 2 subject groups, beats HEALTHCARE |
| `UCLA_Health_Bill` | `financial` ⊂ `financially responsible` → BANKING_FINANCE issuer +2.0 | HEALTHCARE 4.0 vs BANKING 3.0 → gap **1.0**, Phase 5 (rightly) won't override → the $13,857-vs-$472 bug is never fixed |

A wrong domain gets a full issuer score from a coincidental substring.

### M2. Vocabulary collision — the same word claimed by two families

`comprehensive`, `coverage`, `deductible`, `premium`, `patient`,
`procedure` mean one thing in HEALTHCARE and another in INSURANCE, and
both families list them. `Eye_care-invoice` ("R-PT **COMPREHENSIVE**
EXAM", vision **coverage**) → INSURANCE gets a 2-group subject hit while
HEALTHCARE's correct `vision` issuer + `patient` only makes one.
Scoring treats "issuer + 1 generic subject group" identically to
"issuer + 1 specific subject group".

### M3. Taxonomy family gap — the correct domain can't corroborate its own issuer

| doc | correct issuer fires | but no subject/layout term matches → collapses ×0.35 |
|---|---|---|
| `Medixare_Premium_Bill` | GOVERNMENT: `health & human services` ✅ | GOVERNMENT's families are IRS/DMV-shaped ("tax year", "levy", "registration renewal"); a **CMS premium bill** ("delinquent bill", "premium due", "coverage termination", "Medicare number") matches none → GOVERNMENT = 0.70, HEALTHCARE piles on generic medical vocab → **wrong, gap 2.3** |
| `statefarm_bill` | INSURANCE, all correct | HOUSING_PROPERTY has no renters/home-insurance vocab ("renters policy", "residence premises") → HOUSING = 0.0. gap 5.3 — this is a **taxonomy gap, not a low-confidence problem**; INSURANCE is the least-wrong bucket and my HOUSING label is the debatable one |

### M4. Sparse OCR / no issuer — total evidence below the 2.5 floor

| doc | n_el | what's there |
|---|---|---|
| `Coverage_Care_Insurance_Card` | 22 | strong health-plan signals (`PCP Copay`, `Specialist Copay`, `Group Number`, `Plan Type`, `Prescription Group`) but only `copay` is in any family → HEALTHCARE 0.35, INSURANCE 0.70 (literal issuer "Insurance Company") → both below floor → OTHER |
| `Medical_Invoice` | 33 | issuer typo'd ("Zylker **Heathcare**"), service names ("Ambulance service", "Behavioural therapy") in no family → **nothing fires at all** → OTHER |

Not a competition problem — a no-evidence problem.

## The one general fix tested: word-boundary term matching (targets M1)

Shadow classifier `domain_wb.py` — identical to frozen `domain.py` except
term membership uses `\bword\b` (tolerating a trailing plural `s`) instead
of raw substring. Nothing in the frozen pipeline touched.

| | standalone domain agreement | high-conf (gap ≥ 3) | Phase-5 overall | Phase-5 dev | Phase-5 holdout |
|---|---:|---:|---:|---:|---:|
| frozen `domain.py` | 0.84 (42/50) | 29/30 ≈ 97 % | 0.830 | 0.900 | 0.783 |
| `domain_wb.py` | 0.80 (40/50) | **32/33 ≈ 97 %** | **0.830** | 0.900 | 0.783 |

What word-boundary matching actually did:

- **Fixed the mechanism** on the flagged cases: `DMV_Notice` gap 1.0 → **3.65**; `UCLA_Health_Bill` gap 2.0 → **3.0** — which lets Phase 5 finally fix `UCLA total_amount 13857 → 472`.
- **High-confidence accuracy held** at ~97 %.
- **But two regressions**, both on documents that were only *"right by luck"* under substring matching:
  - `Bank_Bill_Due` (a "BUILDING BLOCKS STUDENT HANDOUT / sample credit card statement" with **no bank name**) was classified BANKING_FINANCE solely via `chase` ⊂ `pur`**chase**`s`. Strict matching → OTHER (honest: it has no issuer).
  - `ca-dmv-registration-fee` (a phone photo of a fee screen, `dmv` ⊂ `dmva-dim`, no real letterhead) → OTHER.
- **Net on Phase-5 accuracy: exactly zero** (0.830 → 0.830). The UCLA fix (+1) is offset by one new small hallucination elsewhere; the two degenerate-doc classifications drop out.

## Recommendation — do not change anything yet

The substring-competition mechanism (M1) is **real and confirmed**, and
word-boundary matching is the correct conceptual fix. But on this
50-image sample it **does not improve downstream accuracy** and it costs
two (degenerate) classifications. Per the experiment's own rule — *no
change without evidence it's a net win* — this does not clear the bar.

- **M1**: keep `domain_wb.py` as a documented candidate. Adopt it only if
  a larger real-mail sample shows phantom substring competition is
  frequent enough that the UCLA-class fix outweighs the "lucky guess"
  losses. Cheap to re-test.
- **M2 / M3**: no general fix exists that isn't per-term rule-stacking or
  taxonomy expansion — both explicitly out of scope. These are the
  Phase-4 study's already-noted gaps (Medicare biller-vs-topic; no
  home/renters class). Revisit taxonomy, not the classifier, when more
  data lands.
- **M4**: sparse docs have no reliable signal to rescue; a lone-issuer
  fallback would mostly produce wrong answers (Coverage_Care's only
  issuer is the placeholder string "Insurance Company").

**The load-bearing finding:** low-gap ≠ "classifier needs tuning". Low-gap
correctly reflects that the evidence is genuinely thin or contradictory.
Phase 5's confidence gate already does the right thing with it — defer to
frozen Phase 3. The residual cost is one hard case (UCLA) whose real fix
is upstream precision (word boundaries), pending evidence it generalises.

Artifacts: `domain_wb.py`, `phase6_analyze.py`,
`results/domain/phase6_evidence.json`. Nothing frozen was modified.
