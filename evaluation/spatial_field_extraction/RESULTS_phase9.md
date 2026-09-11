# Phase 9 — End-to-End Evaluation

`image → POST hunyuan-service:8091 /v1/ocr → elements → frozen Phase 3 →
4 → 7 → 8 → final structured result`. Plan B (no `/v1/understand`
orchestrator). Live OCR only — cached OCR never fed to the pipeline.
Phase 3–8 untouched (only `ocr.py` copied into the image).

---

## Phase 9 E2E Result

| | |
|---|---|
| **Dataset** | 50 real US letters (20 dev + 30 holdout), same GT as Phase 5/7/8 |
| **Images** | 50 |
| **Live OCR success** | **49 / 50** — `SoCalGas` failed (HTTP 502, container crashed on the 8192-token request, 2 retries also 502) |
| **OCR truncated** | **1** — `Great_American_Insurance_Invoice` (`finish=length`, and it needed 2 attempts + 294 s) |
| **Overall accuracy** | **0.824** (300 / 364 cells) |
| **Hallucination** | **9** (null-hallucination events) |
| **OCR latency** (49 ok) | min 10 s · **median 61 s · mean 74 s** · p90 142 s · **max 294 s**; 25/49 over 60 s, 7/49 over 120 s |
| **E2E latency** | ≈ OCR latency (frozen pipeline adds < 30 ms/image) |

Offline Phase 7 (cached OCR, 50 img) was **0.830**; Phase 9 E2E (live
OCR, 49 img) is **0.824** — the pipeline behaves the same end-to-end;
the small delta is `SoCalGas` missing + 4 OCR-variation diffs (below).

---

## Per-field

| Field | Accuracy | Error count |
|---|---:|---:|
| Domain | 0.837 | 8 |
| Sender | 0.796 | 10 |
| Recipient | **0.694** | **15** |
| Amount | 0.898 | 5 |
| Payment Status | 0.857 | 7 |
| Due Date | 0.816 | 9 |
| Action | 0.878 | 6 |
| Contact Organization | 0.762 | 5 |
| Contact Type | 0.809 | 4 |
| Phone | 0.809 | 4 |

`answer kinds`: 144 correct · 98 correct-null · 23 null-miss · 20 wrong ·
9 hallucination.

---

## Error Attribution (64 non-ok cells)

| Source | Count | What it is |
|---|---:|---|
| **OCR** (did not read the value) | **4** | `SCE_Sample_Bill` due-date stub, `HOA2` (18-element sparse OCR → no amount candidate), `water_bill` current-charges total, `DMV_Notice` `$83.50` printed only inside a full sentence |
| **OCR truncated** | **1** | `Great_American` action (`please contact …` matched before the cut-off payment-stub text) |
| **Phase 3** (spatial extraction, OCR was correct) | **~28** | **sender**: a Title-Case document heading leaks as the issuer (`Financial Statement`, `HOA DUES INVOICE`, `Membership Renewal Notice`, `QUESTIONS? Please contact us …`, `GEORGIA INSURANCE POLICY INFORMATION CARD`) — ~9. **recipient**: wrong block line / block not detected / label leak (`FINANCIALLY RESPONSIBLE`, `Inspection Site`, `Vehicle Location`, `Coverage Termination Dates`, `Automatic Withdrawal`, `Ohio/West Virginia Markets`, `LINDA DESPAIN` the agent) — ~13. **due_date**: anchor gaps (bare `Due Apr 8 2020`, `remit payment by 11/01/2012`, `DATE DUE SEP 28 2016` lost to `continues policy to JAN 30 2017`) + `10-16-2025` (MM-DD-YYYY with dashes) not parsed — ~6 |
| **Phase 4** (domain, OCR was correct) | **~5** | `Water_Bill2` `Medical_Invoice` `Coverage_Care` → OTHER (sparse OCR), `Eye_care` → INSURANCE (`comprehensive exam` term collision), `aaa-policy_renew` → BANKING (weak signals). Plus a cascade: `UCLA_Health_Bill` amount stays `$13,857` because Phase 4 gives HEALTHCARE only score-gap 1.0 → Phase 7 correctly declines to override |
| **Phase 7** (semantic field, OCR + domain correct) | **~4** | `Auto_Insurance_Bill1` action `pay` from *"amount due"* inside *"will be mailed separately"*; a couple `payment_status` cascades from a nulled amount |
| **Phase 8** (contact / phone) | **~4** | `State_Farm_Insurance`, `statefarm_bill` (agent phones), `aaa-policy_renew`, `DMV_registration_late_fee` — all **safe `null`**, the deliberate "don't reach for a bare / agent number" choice; 0 wrong numbers |
| **GT / boundary** | **~12** | autopay bills marked `paid` vs pipeline `not_applicable`/`unpaid` (`water_bill`, `Medixare`), Medicare healthcare-vs-government split (`Medixare`, `Medicare_of_Denial`), renters-insurance has no HOUSING class (`statefarm_bill`), `aws_invoice` (B2B, no personal domain; `$136.38` vs `$135.38` both printed), `statefarm_bill` action `renew` (arguably more correct than the GT `null`) |

**OCR-caused vs downstream:**
`OCR did not read it → downstream wrong` = **5 cells** (4 + 1 truncated).
`OCR read it correctly → downstream wrong` = **~41 cells** (Phase 3/4/7/8).
GT-debatable = ~12. **The OCR text is right ~95 % of the time an error
occurs; the failure is in the pipeline, and overwhelmingly in Phase 3
sender/recipient.**

---

## Live-vs-cached regression (Step 5)

45 / 49 images produced a **byte-identical final result** from live OCR
vs the earlier cached OCR. This is expected: the frozen pipeline is a
pure function of `elements`, so identical elements → identical output by
construction, and the endpoint's `elements` are byte-identical to
`parse_ocr_elements(raw_content)` (asserted every image).

The 4 diffs are **all OCR-driven**, not pipeline drift:

| image | field | cached → live | cause |
|---|---|---|---|
| `water_bill` | sender | `Water District` → `WATER DISTRICT` | case only; both match GT |
| `DMV_registration_late_fee` | sender | `State of California Department of Public Service Agency` → `a Public Service Agency VIN XXXX…` | live OCR merged the letterhead lines differently |
| `First_Bank_Bill` | recipient | `Mr. Jack Smith` → `null` | live OCR segmented the address block differently → not detected |
| `HOA4` | recipient | `Jane Smith` → `null` | same |

→ HunyuanOCR on the **Docker CPU-only** backend is not bit-reproducible
vs the earlier **native-Metal** cached run (temp 0 does not guarantee
identical CPU-vs-GPU output). ~8 % of images had a materially different
element layout, and on 2 of them that flipped a recipient to `null`.
**Phase 3–8 themselves are unchanged and deterministic.**

---

## The single biggest real bottleneck

**The OCR runtime — the Docker CPU-only llama.cpp container.**

- **Latency**: median **61 s**, mean **74 s**, max **294 s** per image.
  For "拍一张照 → 结果" this is unusable. The old native Metal server did
  the same images in ~10–20 s.
- **Reliability**: the container **crashed twice** during the 50-image
  batch (~every 12–15 heavy multimodal requests); it only completed with
  client-side retry + a 6 s inter-request throttle + `--restart`.
  `SoCalGas` never completed at all — **1/50 total data loss** purely
  from infrastructure.
- **Reproducibility**: CPU-vs-GPU floating point makes the OCR output
  non-deterministic run-to-run, which already flipped 2 recipients.

Everything above this line — the pipeline — is in good shape: **82.4 %
E2E, matching the offline number**, OCR text correct in ~95 % of error
cases, and the accuracy gap is a **known, bounded** set (Phase 3
sender/recipient spatial extraction is ~half of it; the rest is taxonomy
gaps and GT-debatable calls). None of that is the thing blocking a usable
system right now. **The Docker CPU-only OCR is.**

(The *accuracy* bottleneck, once OCR is fast and reliable, is unchanged
from every prior phase: **Phase 3 recipient extraction at 69 %** — wrong
address-block line, or block not detected, or a Title-Case heading
leaking as sender.)

Artifacts: `results/phase9/summary.json`, `results/phase9/raw/*.ocr.json`
(live OCR + timing + raw_content per image).
