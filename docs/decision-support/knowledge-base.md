# RiceGrade demonstration decision-support rules

This is the **implemented UI interpretation layer** in `frontend/src/lib/decisionSupport.ts`. Its rules are transparent and deterministic; adding rules here does not claim professional review, research validation, or official certification. All outputs should remain explainable and support the operator's judgment.

## Inputs

- `total_milling_recovery` — computed in the Pages backend from the measured total milled-rice output and measured paddy input, in percentage points.
- `head_rice_recovery` — optional; computed from measured head-rice output divided by measured paddy input, in percentage points.
- `moisture_content` — optional externally measured paddy moisture reading; never inferred from an RGB image.
- `counts` and `count_percentages` — four mutually exclusive XGBoost image classes. Count percentages are **not** measurements by weight.

## Rules and source basis

| Condition | Observed finding | Displayed suggestion |
|---|---|---|
| Total recovery < 65.1% | Explicit measured shortfall in percentage points | Review recovery, sample weighing, output collection, separation, husking and milling losses |
| Total recovery >= 65.1% | Reference met | Review other quality indicators and recorded operating conditions |
| Head recovery present and < 48% | Explicit measured shortfall | Review head-rice breakage, husking, whitening and feed conditions |
| Head recovery present and >= 48% | Reference met | Continue reviewing head-rice output |
| Head recovery absent | No head-rice comparison made | No fabricated measurement or threshold result |
| Image result includes non-whole grains | Largest non-whole category by **count**, not weight | Suggest inspection of stage or QA/QC review corresponding to observed class |
| Paddy moisture recorded | Display recorded value | Compare with appropriate paddy/equipment protocol; **do not compare with milled-rice product moisture limit** |

The 65.1% and 48% reference values are reported by the Philippine Rice Research Institute for **breeding operations / varietal evaluation**, not universal mill targets or official PNS grading of a particular milling lot.

Source: [PhilRice Rice Breeding Operations Manual](https://www.philrice.gov.ph/rice-breeding-operations-manual/), milling recovery section and Table 12.1.

## Exclusions

- Do not assert an official grade from grain-count proportions.
- Do not infer a causal machine fault from the image alone.
- Do not automatically direct the user to repeat test milling.
- Do not invent unmeasured moisture, weights, machine settings, or expert approvals.
- Do not claim the model has been calibrated or validated by a specialist simply because a value appears in the app.

## Workflow

1. Save the assessment and physical measurements through the current Pages API.
2. Upload a rice-sample photo to R2.
3. POST the screening request to the ML Worker through the existing Pages API.
4. Present the saved model predictions as four class counts and percentages plus detected outlines and labels.
5. Evaluate these deterministic recommendations using the recorded measurement values and the saved image-screening result; present both in the same result view.

If the image upload or ML call fails, the assessment remains saved, and the UI exposes that error rather than inventing classifications. The shared `AssessmentInsights` component shows only data available for that assessment.
