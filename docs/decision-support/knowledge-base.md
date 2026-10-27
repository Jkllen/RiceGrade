# RiceGrade decision-support rules

The system's decision support is the deterministic rule engine in `frontend/src/lib/dss.ts`, displayed by `frontend/src/components/ui/AssessmentInsights.tsx` on the Analysis, History and Reports pages. The same inputs always give the same outcome. Boundary tests: `npm run test:dss` (in `frontend/`).

RiceGrade does not grade rice. The rules turn the four-class image screening (whole, broken, chalky, discolored) and the measured recovery into suggested actions.

## Inputs

- **Paddy input and total milled rice weights** in grams, measured. Required.
- **Head rice weight** in grams, measured. Optional; R8 is skipped without it.
- **Image screening result**: per-grain class (whole, broken, chalky, discolored) and XGBoost top-class score. Percentages are **by grain count, not weight**.
- **Retest**: an earlier test run of the same lot ID (case- and space-insensitive) exists.

## Thresholds

| Check | Threshold | Basis |
|---|---|---|
| Broken % (count) | Above 15%; severe above 45% | Reference limit from PNS/BAFS 290:2019 Table 2. Broken pieces weigh less than whole grains, so count shares run higher than weight shares; using the weight limit on counts errs toward flagging, the safe direction for screening. |
| Chalky % (count) | Above 7% | Same reference. Chalky and whole kernels weigh about the same, so count and weight shares are close. |
| Discolored % (count) | Above 1% | Same reference. |
| Uncertain grain | Top-class score below 0.60 | Project-set. The model's scores are uncalibrated. |
| Too many uncertain grains | More than 10% of grains | Project-set. |
| Too few grains | Fewer than 100 accepted grains | PABES 304 100-kernel sets. |
| Close to a limit | Within ±2 percentage points of a limit; for limits under 4%, within ±half the limit | Project-set. A flat ±2 band around the 1% discolored limit would include 0%, so Proceed could never be reached. |

## Rules

| # | If | Outcome | Action / stage to review |
|---|---|---|---|
| R1 | Fewer than 100 grains, >10% uncertain, no screening result, missing weights, or impossible weights (milled > paddy, head > milled) | Manual Verification (blocks the assessment when inputs are missing or impossible) | Recapture the image or re-weigh the samples |
| R2 | Recovery below 62% | Manual Verification first | Check the weights, output collection and test-milling procedure. If confirmed (panel checkbox), apply R6 |
| R3 | Chalky above 7% | QA Review | Input concern: chalkiness comes from the grain, not milling |
| R4 | Discolored above 1% | QA Review | Input concern: PNS defines discoloration as caused by heating; check drying and storage |
| R5 | Broken above 15% on a retest after an adjustment | QA Review | The paddy may already be cracked or fissured |
| R6 | Recovery 62% to under 65% | Review / Adjust and Retest | Husking (rubber-roll clearance), whitening/polishing intensity, sifting |
| R7 | Broken above 15%, first test | Review / Adjust and Retest | Whitening/polishing intensity, rubber-roll husking, feed rate |
| R8 | Head rice below 50% of **milled** rice | Review / Adjust and Retest | Whitening/polishing, husking |
| R10 | Within the near-limit band of any limit | Review / Adjust and Retest | Take another sample before deciding |
| R11 | None of the above | Proceed to Full-Scale Milling | None |

R9 (paddy grains per kg) is not used: it is not one of the four image classes, and all measurements are entered in grams.

Several rules can fire together. The overall outcome is the most serious one: Manual Verification > QA Review > Review / Adjust and Retest > Proceed.

## Boundaries

- No rice grade is assigned. The PNS/BAFS 290:2019 values are used only as reference limits for the count-based suggestions.
- Recovery rules (R2, R6, R8) use measured weights only, never image counts.
- Head rice in R8 is a share of total milled rice. The stored `head_rice_recovery` field is a share of paddy, so the two numbers differ.
- The R2 confirmation checkbox is not saved with the assessment.

## Changes from the earlier interpretation layer

This replaces the earlier `decisionSupport.ts`, which compared total recovery with 65.1% and head-rice recovery with 48% (PhilRice Rice Breeding Operations Manual, Table 12.1) and gave findings without an outcome. Those PhilRice values are breeding/varietal-evaluation references, not mill targets, and are no longer used as decision thresholds.

Source for the 15% / 7% / 1% reference limits: PNS/BAFS 290:2019, *Grains – Grading and classification – Paddy and milled rice*, Table 2.
