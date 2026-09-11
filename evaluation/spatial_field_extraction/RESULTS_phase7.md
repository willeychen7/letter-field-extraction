# Phase 7 — Domain-Aware Field Semantics (stable layer)

Goal: take the capability Phase 5 validated and turn it from scattered
experimental code into **one declarative semantic layer with a documented
contract**. Not a new classifier. No new rules beyond what Phase 5 proved.
Phase 3–6 untouched.

Deliverables: (A) architecture, (B) the declarative contract, (C) error
analysis, (D) controlled experiment proving the consolidation is faithful.

---

## A. Architecture

```
HunyuanOCR  (text + bbox)                              [frozen]
   │
   ▼
Spatial Field Extraction   (Phase 3)                   [frozen]
   │   → per-field candidates + geometric scores + evidence
   │   → sender · recipient · total_amount · payment_status · due_date · action
   ▼
Domain Classification      (Phase 4, 7 classes)        [frozen]
   │   → domain ∈ {INSURANCE, HEALTHCARE, BANKING_FINANCE, GOVERNMENT,
   │               UTILITIES_SERVICES, HOUSING_PROPERTY, OTHER}
   │   → confidence = score gap between the top two domains
   ▼
Domain-Aware Field Semantics   (Phase 7)               ← THIS LAYER
   │   for total_amount / payment_status / action only:
   │     · drop candidates whose row-label is domain-inadmissible
   │     · if the domain has no "amount due" concept present → not_applicable
   │     · remap action to the domain-meaningful verb (renewal → renew)
   │   gated by domain confidence; low confidence → pass frozen through
   ▼
Field result  { value, status, reason, domain, confidence }
     status ∈ { resolved , not_applicable , insufficient_evidence }
```

Why the layer sits **after** extraction and classification, not inside
them: the frozen layers answer *"what numbers/dates are on the page and
where"* and *"who is this from"*. Only with both known can you answer
*"which of those numbers is the thing this person owes"* — and that
answer is domain-specific (`Ending Balance` on a bank statement vs a
utility bill).

### Layer contract

| property | guarantee |
|---|---|
| never invents | only keeps/drops candidates Phase 3 already scored |
| never overrides on a shaky domain | acts only when gap ≥ 1.5, or domain ∈ {BANKING_FINANCE, UTILITIES_SERVICES} (0 misclassifications in Phase 4); otherwise frozen passes through |
| scoped | touches only `total_amount`, `payment_status`, `action` |
| pass-through | `sender`, `recipient`, `due_date` are frozen Phase 3 verbatim — Phase 5 showed domain gives no reliable signal for them |
| explainable | every field carries a `reason` string and a `status` |

The `status` is the product-facing value: it lets the Chinese-summary
layer say a number (`resolved`), say "这不是账单" (`not_applicable`), or
say "看不准" (`insufficient_evidence`) — three different messages that a
bare `null` cannot distinguish.

---

## B. The declarative contract (`field_semantics.py :: SEMANTICS`)

One table, keyed by domain. Vocabulary only — no image-specific values.

| domain | amount: EXCLUDE if row-label contains | amount: REQUIRE (one must appear, else null) | payment_status when nothing owed | action |
|---|---|---|---|---|
| **BANKING_FINANCE** | ending/beginning/opening/closing/available balance, balance forward, previous balance, (total) credit line/available/access | amount due · minimum payment due · payment due · new balance total · total minimum payment · … | **not_applicable** (a statement is not a bill) | — |
| **HEALTHCARE** | total (current) charges · provider charges · insurance paid/payment/adjustment/pending · allowed charges · patient payments · adjustments · total claim cost | amount you owe · patient responsibility · your responsibility · balance due · due from patient · responsibility to pay · … | **not_applicable** (EOB / MSN) | — |
| **INSURANCE** | premium · coverage · deductible · limits · bodily injury · property damage · six-month premium · collision · comprehensive · fees | amount due · premium due · minimum due · total amount owed · balance due · amount owed · … | **not_applicable** (declarations / card) | **renew** on renewal context |
| **GOVERNMENT** | registration/license/weight/plate/smog fee · county/district · owner responsibility fee · prior balance | amount due (immediately/by) · total due (on or before) · balance due · restoration fee · … | leave to frozen (a levy / bill is real) | **renew** on renewal context |
| **UTILITIES_SERVICES** | previous balance · budget · payments received/and other | amount due · total due · current charges · your new charges · balance due · payment is due · amount enclosed · … | leave to frozen | — |
| **HOUSING_PROPERTY** | *(no amount constraint — HOA dues behave like utilities; frozen amount logic kept)* | — | leave to frozen | — |
| **OTHER** | *(no constraint — pure frozen pass-through)* | — | leave to frozen | — |

Domain-independent: any doc containing an explicit not-a-bill structural
marker (`THIS IS NOT A BILL`, `EXPLANATION OF BENEFITS`, `DECLARATIONS
PAGE`, `FINANCIAL STATEMENT`, `RATES & CHARGES`, `ESTIMATE ID`, `PAYMENT
IS NOT REQUIRED`, …) → `total_amount = null`, `payment_status =
not_applicable`.

---

## C. Controlled experiment

### C.1 Faithfulness — does the declarative layer == frozen Phase 5?

`run_phase7.py` computes every field two ways — frozen `phase5.py` and
the new `field_semantics.py` — on all 50 images.

> **IDENTICAL on all 50 × 6 cells.** The consolidation is exact; no
> behaviour was gained or lost in the rewrite.

### C.2 Scoring — vs frozen Phase 3 baseline

| field | baseline | Phase 7 | Δ |
|---|---:|---:|---:|
| sender | 0.800 | 0.800 | — |
| recipient | 0.740 | 0.740 | — |
| **total_amount** | 0.780 | **0.900** | **+0.120** |
| **payment_status** | 0.680 | **0.840** | **+0.160** |
| due_date | 0.820 | 0.820 | — |
| action | 0.880 | 0.880 | — |
| **OVERALL** | **0.783** | **0.830** | **+0.047** |

dev 0.892 → 0.900 · holdout 0.711 → 0.783 · hallucination events 15 → 9 ·
wrong 28 → 21 · **0 dev regressions, 0 breaks** (identical to Phase 5).

---

## D. Error analysis — where do the remaining errors live?

19 non-correct cells on the layer's three owned fields, bucketed by
*whose* problem it is:

| bucket | count | the layer's job? |
|---|---:|---|
| **upstream — Phase-4 domain wrong** | 4 | no. Medixare→HEALTHCARE, Water_Bill2→OTHER, aws→UTILITIES, statefarm→INSURANCE. Wrong domain ⇒ wrong constraint. |
| **upstream — domain low-confidence, layer deferred** | 5 | no (by design). DMV_Notice (gap 1.0 ×3), SCE_Letter (gap 0.0), **UCLA_Health_Bill** (gap 1.0 — the `$13,857` vs `$472` case; the layer *correctly* declines to act on a shaky HEALTHCARE call). |
| **upstream — Phase-3 candidate wrong, nothing better to pick** | 3 | no. SoCalGas / water_bill payment (autopay GT + truncated OCR), Great_American action (truncated OCR). |
| **semantic-layer gap / GT-debatable** | 7 | partly. See below. |

The 7 in the layer's remit:

| case | verdict |
|---|---|
| `Auto_Insurance_Bill1` action `pay` vs None | **real layer gap** — a candidate general rule: if the domain resolved `total_amount` to `null / not_applicable`, an action of `pay` is inconsistent → downgrade. Principled, not per-image. |
| `HOA2` amount / payment_status `null` | Phase-3 produced no candidate (18-element OCR, year "2085"); HOUSING has no amount spec. Needs a HOUSING amount contract *or* is upstream. |
| `water_bill` amount `null` vs `71.20` | UTILITIES REQUIRE list may miss the anchor this bill uses — needs verification it isn't just a Phase-3 miss. |
| `AAA_insurance_Bill` action, `Medicare_Notice_of_Denial` action, `DMV_registration_late_fee` payment_status | frozen-action gaps or GT-debatable (redacted values / "appeal" vs "call"). Not domain-semantics. |

**Reading:** 12 of 19 residual errors are provably upstream (Phase 3 OCR/
extraction or Phase 4 classification) — exactly the layers Phase 7 is
designed *not* to touch. The semantic layer's own remaining debt is
~1–2 real rules (`pay`-action consistency with a null amount; a HOUSING
amount contract), both general.

---

## Status

- **`field_semantics.py` is the stable form of Phase 5** — same numbers,
  bit-exact, but now a single declarative table + a documented contract
  with `{value, status, reason}` output. Frozen in `frozen_phase7/`.
- The pipeline is now:
  `OCR+bbox → Spatial Extraction → Domain → Domain-Aware Field Semantics
   → Amount / Status / Due Date / Action`, each stage frozen and
  independently testable.
- Next stage (separate): `Action → Contact Organization → Phone Number`.
- Not done here (deliberately): no Phase 3–6 change, no domain-classifier
  work, no semantic similarity, no re-OCR, no per-image special cases.
