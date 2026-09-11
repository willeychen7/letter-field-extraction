# Phase 4 (research) — Document Domain / Category taxonomy

Goal: test whether an 8-class *life-domain* taxonomy is natural and stable.
No rule tuning to any set. **Phase 3 stays fully frozen.** Amount / due
date / payment status are NOT reconnected.

Method: hand-label all 50 benchmark images (20 dev + 30 holdout) by
document content → `gt_domain.py`. Build a deterministic multi-signal
classifier (`domain.py`) that scores each class from 3 independent
evidence groups — **issuer**, **subject**, **layout** — and needs
corroboration across ≥ 2 groups to fire. Compare, inspect the disagreements.

## Numbers

| | agreement w/ hand labels |
|---|---:|
| all 50 | **41/50 = 82 %** |
| dev 20 | 18/20 = 90 % |
| holdout 30 | 23/30 = 77 % |
| when classifier is **confident** (score gap ≥ 3) | **31/32 = 97 %** |
| when **shaky** (gap < 1.5) | 6/11 |

The 13-point dev→holdout drop is **concentrated in the failure modes
below**, not a broad collapse — unlike Phase-3 field extraction, domain
classification largely held up on unseen mail.

## 1. Which images classify easily

~32/50, with a large score gap and correct: **utility bills** (SCE,
SoCalGas, water, waste, AT&T), **HOA dues** (all 4), **bank checking
statements** (Chase ×2, EastWest, First Bank), **auto policy /
declarations / cards** (Allstate, Farmers, State Farm, Penny), **IRS
notices**, **Medicare Summary Notices**, **DMV notices**, **EOB**.

Common factor: a **named institutional issuer in the letterhead** + a
**document structure that only that domain uses** (a usage/meter table, a
checking summary, a coverage table with VIN, an EOB claim grid, an HOA
dues line). When both are present the decision is unambiguous.

## 2. Which categories confuse each other

| pair | why | example |
|---|---|---|
| **HEALTHCARE ↔ AUTO_INSURANCE** | shared vocabulary: *comprehensive, deductible, coverage, claim, premium, policy* mean different things in each | `Eye_care-invoice` ("R-PT COMPREHENSIVE EXAM") → AUTO_INSURANCE |
| **HEALTHCARE ↔ GOVERNMENT_TAX** | Medicare/CMS is both a health topic and a government biller | `Medixare_Premium_Bill` (CMS premium delinquent bill) → HEALTHCARE; I labeled it GOVERNMENT_TAX — and that call is itself debatable |
| **CREDIT_CARD ↔ BANKING_FINANCE** | both bank-issued; only *credit limit / minimum payment / APR* vs *checking / balance* separates them | `Bank_Bill_Example` (a card statement) → BANKING_FINANCE |
| **AUTO_INSURANCE ↔ HOUSING_PROPERTY** | renters/home insurance has no home in the taxonomy, so it lands with auto | `statefarm_bill` ("Renters Policy") → AUTO_INSURANCE |
| **any ↔ OTHER** | sparse OCR / no issuer word → nothing corroborates | `Medical_Invoice`, `Coverage_Care_Insurance_Card` (health cards with only copays) → OTHER |

## 3. Which categories should merge

- **CREDIT_CARD → fold into BANKING_FINANCE.** The split is fragile (1 of
  3 already misfired), both are financial-institution accounts, and at the
  *domain* level a reader needs "this is about a bank account / card I
  hold" — the card-vs-checking distinction belongs to a later obligation
  layer, not the domain. → one `BANKING_FINANCE` (7 images, clean).
- **AUTO_INSURANCE → broaden to `INSURANCE`.** Of 9 "AUTO_INSURANCE"
  labels, 3 aren't auto (AAA umbrella, a generic commercial premium
  invoice, renters). The domain the mail actually needs is *personal
  insurance* (policy / bill / card / claim / renewal), with auto / home /
  life as a **sub-type resolved later**. Forcing "AUTO" creates wrong
  labels at the top level.

Net: **8 → 7 classes** (INSURANCE, HEALTHCARE, BANKING_FINANCE,
GOVERNMENT_TAX, UTILITIES_SERVICES, HOUSING_PROPERTY, OTHER), and the
Medicare cases stay a deliberate HEALTHCARE-vs-GOVERNMENT_TAX call driven
by *who is billing / notifying* (a provider or a plan → HEALTHCARE; SSA /
CMS acting as premium biller or enrollment authority → GOVERNMENT_TAX).

## 4. Missing domains

- **General INSURANCE** (home / renters / life / umbrella / liability) —
  ~4 images have no honest bucket. (Addressed by merge #3.)
- **MEMBERSHIP / SUBSCRIPTION / RECURRING SERVICE** — AAA roadside
  membership, AWS cloud, and (real-world) gym / streaming / warranty.
  Not a utility, not one of the other 7. Currently → OTHER or wrongly →
  UTILITIES.
- **Coverage risk, not in this sample**: pension / retirement, legal /
  court, education, employment/HR mail. Plausible in real elderly mail;
  the taxonomy has no slot and would dump them in OTHER.

## 5. OTHER share

- Hand-labeled **gold OTHER: 2/50 (4 %)** — an SCE→regulator letter, the
  AWS invoice.
- Classifier **predicted OTHER: 5/50 (10 %)** — it adds the sparse
  medical invoice, sparse health card, the water-bill handout, and the
  AAA membership.

So OTHER is doing two jobs: (a) genuinely uncategorizable (~4 %), and
(b) **"OCR too thin to corroborate"** (~6 %). With complete OCR the real
uncategorizable rate looks like ~5 %; the inflation is a signal-strength
problem, not a taxonomy problem.

## 6. Is this better than PAYMENT / STATEMENT / NOTICE / BENEFIT_OR_COVERAGE

**Yes — and they are complementary, not competitors.**

- The old 4 classify document **form / obligation**: is it asking for
  money, informing me, or notifying me. That axis **flips for the same
  document** depending on wording (an SCE bill vs an SCE late notice vs an
  SCE shutoff warning move between PAYMENT and NOTICE).
- The 7 domains classify **life area / source**: which of my accounts is
  this, who is it from. This axis is **anchored to the letterhead** — the
  most reliable OCR signal — so it is stable across a bill / reminder /
  final notice from the same issuer, and it held up dev→holdout (90 % →
  77 %) far better than Phase-3 structure did (89 % → 71 %).
- For the product goal (help a confused reader), **domain is the better
  primary axis**: "this is your electricity / your hospital / your bank /
  the government" is the first thing that orients someone. The
  obligation layer then becomes a small **second axis** (≈ OWES_MONEY /
  INFORMATIONAL / ACTION_NO_MONEY), not a 4-way form taxonomy.

## Recommendation for the taxonomy

1. Adopt **7 classes**: `INSURANCE`, `HEALTHCARE`, `BANKING_FINANCE`,
   `GOVERNMENT_TAX`, `UTILITIES_SERVICES`, `HOUSING_PROPERTY`, `OTHER`
   (drop `CREDIT_CARD` and `AUTO_INSURANCE` as top-level).
2. Add **`MEMBERSHIP_SERVICES`** only if more real samples (AAA, AWS,
   subscriptions) show it is a recurring category — otherwise leave in
   OTHER and revisit.
3. Keep Medicare/CMS as an explicit **issuer-driven** HEALTHCARE vs
   GOVERNMENT_TAX rule, not a keyword.
4. The classifier's own **score gap is a usable confidence signal** —
   97 % correct when gap ≥ 3. A low-gap result should be surfaced as
   "uncertain domain", not a silent guess.
5. Domain becomes the primary axis; obligation/form is a separate, smaller
   axis layered on top — do NOT rebuild the 4-way PAYMENT/STATEMENT/…
   taxonomy.

Nothing was changed in the frozen pipeline. Artifacts in
`results/domain/summary.json` (+ per-row evidence).
