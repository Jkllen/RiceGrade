import type { Evaluation, ScreeningResult } from "./evaluations";

/** Reference comparisons; not a prediction of cause or an official rice grade. */
export type DecisionItem = {
  title: string;
  observation: string;
  action: string;
  source: string;
  priority: "attention" | "review" | "info";
};
export const TOTAL_RECOVERY_REFERENCE = 65.1;
export const HEAD_RECOVERY_REFERENCE = 48;

export function buildDecisionSupport(
  evaluation: Evaluation,
  screening: ScreeningResult | null,
): DecisionItem[] {
  const items: DecisionItem[] = [];
  const total = evaluation.total_milling_recovery;
  if (total < TOTAL_RECOVERY_REFERENCE) {
    items.push({
      title: "Review total milling recovery",
      observation: `Measured recovery is ${total.toFixed(2)}%, which is ${(TOTAL_RECOVERY_REFERENCE - total).toFixed(2)} percentage points below the ${TOTAL_RECOVERY_REFERENCE}% reference.`,
      action:
        "Check collection and weighing of all milled-rice streams; review paddy separation, husking and milling losses with the operator.",
      source: "PhilRice breeding-operations recovery reference",
      priority: "attention",
    });
  } else {
    items.push({
      title: "Total recovery meets the reference",
      observation: `Measured recovery is ${total.toFixed(2)}%, meeting the ${TOTAL_RECOVERY_REFERENCE}% reference by ${(total - TOTAL_RECOVERY_REFERENCE).toFixed(2)} percentage points.`,
      action:
        "Maintain the recorded operating conditions and review the remaining quality indicators before making production decisions.",
      source: "PhilRice breeding-operations recovery reference",
      priority: "info",
    });
  }
  if (evaluation.head_rice_recovery != null) {
    const head = evaluation.head_rice_recovery;
    items.push(
      head < HEAD_RECOVERY_REFERENCE
        ? {
            title: "Review head-rice recovery",
            observation: `Measured head-rice recovery is ${head.toFixed(2)}%, ${(HEAD_RECOVERY_REFERENCE - head).toFixed(2)} percentage points below the ${HEAD_RECOVERY_REFERENCE}% reference.`,
            action:
              "Inspect grain breakage and relevant husking and whitening conditions, including feed consistency and equipment adjustment, before deciding on operational changes.",
            source: "PhilRice breeding-operations recovery reference",
            priority: "attention",
          }
        : {
            title: "Head-rice recovery meets the reference",
            observation: `Measured head-rice recovery is ${head.toFixed(2)}%, meeting the ${HEAD_RECOVERY_REFERENCE}% reference.`,
            action:
              "Continue monitoring head-rice output and the observed sample quality.",
            source: "PhilRice breeding-operations recovery reference",
            priority: "info",
          },
    );
  }
  if (screening && screening.total_grains > 0) {
    const names: Record<string, string> = {
      broken_grain: "Broken",
      chalky_grain: "Chalky",
      discolored_grain: "Discolored",
    };
    const findings = Object.entries(names)
      .map(([id, label]) => ({
        id,
        label,
        count: screening.counts[id] ?? 0,
        share: screening.count_percentages[id] ?? 0,
      }))
      .filter((row) => row.count > 0)
      .sort((a, b) => b.count - a.count);
    if (findings.length) {
      const leading = findings[0];
      const actions: Record<string, string> = {
        broken_grain:
          "Review handling and milling stages that may contribute to breakage; compare findings with the measured head-rice output when available.",
        chalky_grain:
          "Record the visible chalkiness and consult QA/QC regarding source-lot characteristics and appropriate sorting or handling.",
        discolored_grain:
          "Refer the visibly discolored fraction for QA/QC inspection and appropriate sorting or segregation decisions.",
      };
      items.push({
        title: `${leading.label} is the largest non-whole group`,
        observation: `${leading.count} of ${screening.total_grains} classified objects (${leading.share.toFixed(1)}% by count) were labeled ${leading.label.toLowerCase()}.`,
        action: actions[leading.id],
        source: "RiceGrade image classification · grain-count basis",
        priority: "review",
      });
    } else {
      items.push({
        title: "Visual distribution",
        observation: `All ${screening.total_grains} classified objects are labeled Whole.`,
        action:
          "Review the annotated sample alongside your physical recovery measurements.",
        source: "RiceGrade image classification · grain-count basis",
        priority: "info",
      });
    }
  }
  return items;
}
