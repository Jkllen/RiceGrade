/**
 * Deterministic RiceGrade decision-support rules (R1–R11; R9 is not used).
 * Visual rules act on the four-class model's grain COUNTS (whole, broken, chalky, discolored)
 * and recovery rules act on measured weights in grams. No rice grade is assigned.
 */
import type { Evaluation, ScreeningResult } from './evaluations';

/** Count-based limits for the visual classes. Values follow PNS/BAFS 290:2019 Table 2 (Grade No. 2 column). */
export const VISUAL_LIMITS = { broken: 15, chalky: 7, discolored: 1 } as const;

export const DSS_THRESHOLDS = {
  severeBrokenCountPct: 45,
  uncertainScore: 0.6,
  maxUncertainPct: 10,
  minGrains: 100,
  nearLimitPoints: 2,
  recoveryVerifyBelow: 62,
  recoveryTarget: 65,
  minHeadShareOfMilled: 50,
} as const;

export type DssOutcome = 'manual_verification' | 'qa_review' | 'adjust_retest' | 'proceed';
export type DssRule = 'R1' | 'R2' | 'R3' | 'R4' | 'R5' | 'R6' | 'R7' | 'R8' | 'R10' | 'R11';
export type DssSource = 'measured_weights' | 'pns_reference_count' | 'pabes_304' | 'project_set';
export type DssFinding = {
  rule: DssRule;
  outcome: DssOutcome;
  severe: boolean;
  title: string;
  explanation: string;
  action: string;
  source: DssSource;
};
export type DssMetrics = {
  totalRecovery: number | null;
  headShareOfMilled: number | null;
  brokenCountPct: number | null;
  chalkyCountPct: number | null;
  discoloredCountPct: number | null;
  uncertainPct: number | null;
  grains: number | null;
};
export type DssResult = {
  outcome: DssOutcome;
  /** True when critical inputs are missing or impossible; the outcome must not be read as a milling decision. */
  blocked: boolean;
  findings: DssFinding[];
  notEvaluated: string[];
  metrics: DssMetrics;
  isRetest: boolean;
};
export type DssInput = {
  evaluation: Evaluation;
  screening: ScreeningResult | null;
  isRetest: boolean;
  /** Operator has re-checked weights and procedure after an R2 flag. */
  recoveryConfirmed?: boolean;
};

export const OUTCOME_LABELS: Record<DssOutcome, string> = {
  manual_verification: 'Manual Verification',
  qa_review: 'QA Review',
  adjust_retest: 'Review / Adjust and Retest',
  proceed: 'Proceed to Full-Scale Milling',
};
export const SOURCE_LABELS: Record<DssSource, string> = {
  measured_weights: 'Measured weights',
  pns_reference_count: 'PNS/BAFS 290:2019 reference limit, applied to grain counts',
  pabes_304: 'PABES 304 (100-kernel sets)',
  project_set: 'Project-set',
};
const RANK: Record<DssOutcome, number> = { manual_verification: 3, qa_review: 2, adjust_retest: 1, proceed: 0 };

// Rounding to 1e-6 keeps boundary cases such as 650 g / 1000 g from landing on 65.00000000000001.
const pct = (part: number, whole: number) => Math.round((part / whole) * 100 * 1e6) / 1e6;
const fmt = (value: number) => `${Number(value.toFixed(2))}%`;
const positive = (value: unknown): value is number => typeof value === 'number' && Number.isFinite(value) && value > 0;

/** A later test run of the same lot. Earlier runs are assumed to have been followed by an adjustment. */
export function isRetestOf(evaluation: Evaluation, all: Evaluation[]): boolean {
  const lot = evaluation.lot_id.trim().toLowerCase();
  const key = (e: Evaluation) => `${e.test_date}|${e.created_at}|${String(e.id).padStart(12, '0')}`;
  return all.some(other => other.id !== evaluation.id && other.lot_id.trim().toLowerCase() === lot && key(other) < key(evaluation));
}

export function evaluateDss({ evaluation: e, screening, isRetest, recoveryConfirmed = false }: DssInput): DssResult {
  const t = DSS_THRESHOLDS;
  const limits = VISUAL_LIMITS;
  const findings: DssFinding[] = [];
  const notEvaluated: string[] = [];
  const add = (f: Omit<DssFinding, 'severe'> & { severe?: boolean }) => findings.push({ severe: false, ...f });
  const verify = (title: string, explanation: string, action: string, source: DssSource = 'measured_weights') =>
    add({ rule: 'R1', outcome: 'manual_verification', title, explanation, action, source });

  // R1 — weights. Any failure blocks the recovery rules, since recovery cannot be trusted.
  const reweigh = 'Re-weigh the samples and correct the saved measurements.';
  let weightsValid = true;
  if (!positive(e.paddy_input_weight)) { weightsValid = false; verify('Paddy input weight missing or invalid', 'Total recovery needs a positive paddy input weight.', reweigh); }
  if (!positive(e.total_milled_rice_weight)) { weightsValid = false; verify('Milled rice weight missing or invalid', 'Total recovery needs a positive milled rice weight.', reweigh); }
  if (weightsValid && e.total_milled_rice_weight > e.paddy_input_weight) { weightsValid = false; verify('Milled rice exceeds paddy input', `Milled rice (${e.total_milled_rice_weight} g) cannot weigh more than paddy input (${e.paddy_input_weight} g).`, reweigh); }
  if (e.head_rice_weight !== null && (!positive(e.head_rice_weight) || (weightsValid && e.head_rice_weight > e.total_milled_rice_weight))) { weightsValid = false; verify('Head rice weight impossible', 'Head rice must be positive and cannot weigh more than total milled rice.', reweigh); }
  if (e.brown_rice_weight !== null && (!positive(e.brown_rice_weight) || (weightsValid && (e.brown_rice_weight < e.total_milled_rice_weight || e.brown_rice_weight > e.paddy_input_weight)))) { weightsValid = false; verify('Brown rice weight impossible', 'Brown rice must lie between the milled rice weight and the paddy input weight.', reweigh); }

  // R1 — image screening reliability.
  let grains: number | null = null, uncertainPct: number | null = null;
  let broken: number | null = null, chalky: number | null = null, discolored: number | null = null;
  if (!screening) {
    verify('No grain screening result', `Visual rules need at least ${t.minGrains} screened grains; none are available.`, 'Attach a sample image and run grain screening.', 'pabes_304');
    notEvaluated.push('R3–R5, R7 and visual R10: no grain screening result');
  } else {
    grains = screening.total_grains;
    const share = (name: string) => pct(screening.counts[name] ?? 0, grains!);
    broken = share('broken_grain'); chalky = share('chalky_grain'); discolored = share('discolored_grain');
    uncertainPct = pct(screening.grains.filter(g => g.score < t.uncertainScore).length, grains);
    if (grains < t.minGrains) verify('Too few grains', `${grains} grains were accepted; at least ${t.minGrains} are needed.`, 'Recapture the image with more separated grains.', 'pabes_304');
    if (uncertainPct > t.maxUncertainPct) verify('Too many uncertain grains', `${fmt(uncertainPct)} of grains have a top-class score below ${t.uncertainScore} (limit ${t.maxUncertainPct}%). Scores are uncalibrated.`, 'Recapture the image, or check the uncertain grains by hand.', 'project_set');
  }

  // R2 / R6 — total recovery from measured weights.
  let recovery: number | null = null, headShare: number | null = null;
  if (weightsValid) {
    recovery = pct(e.total_milled_rice_weight, e.paddy_input_weight);
    if (recovery < t.recoveryVerifyBelow && !recoveryConfirmed) {
      add({ rule: 'R2', outcome: 'manual_verification', title: `Recovery below ${t.recoveryVerifyBelow}%`, explanation: `Total milled-rice recovery is ${fmt(recovery)}.`, action: 'Check the weights, how output was collected, and the test-milling procedure. If the numbers are confirmed, R6 applies.', source: 'project_set' });
    } else if (recovery < t.recoveryTarget) {
      const confirmedLow = recovery < t.recoveryVerifyBelow;
      add({ rule: 'R6', outcome: 'adjust_retest', title: confirmedLow ? `Confirmed recovery below ${t.recoveryVerifyBelow}%` : `Recovery ${t.recoveryVerifyBelow}% to under ${t.recoveryTarget}%`, explanation: `Total milled-rice recovery is ${fmt(recovery)}${confirmedLow ? '; the operator confirmed the weights (R2 → R6)' : ''}.`, action: 'Review husking (rubber-roll clearance), whitening/polishing intensity, and sifting.', source: 'project_set' });
    }
    // R8 — head rice as a share of milled rice, not of paddy.
    if (e.head_rice_weight === null) notEvaluated.push('R8: head rice weight not measured');
    else {
      headShare = pct(e.head_rice_weight, e.total_milled_rice_weight);
      if (headShare < t.minHeadShareOfMilled) add({ rule: 'R8', outcome: 'adjust_retest', title: `Head rice below ${t.minHeadShareOfMilled}% of milled rice`, explanation: `Head rice is ${fmt(headShare)} of total milled rice.`, action: 'Review whitening/polishing and husking.', source: 'project_set' });
    }
  } else notEvaluated.push('R2, R6, R8 and recovery R10: weights failed validation');

  // R3 / R4 / R5 / R7 — four-class visual screening, by grain count.
  if (screening) {
    if (chalky! > limits.chalky) add({ rule: 'R3', outcome: 'qa_review', title: 'Chalky grains above limit', explanation: `${fmt(chalky!)} chalky by count (limit ${limits.chalky}%).`, action: 'Input concern: chalkiness comes from the grain itself, not from milling. Review the paddy source.', source: 'pns_reference_count' });
    if (discolored! > limits.discolored) add({ rule: 'R4', outcome: 'qa_review', title: 'Discolored grains above limit', explanation: `${fmt(discolored!)} discolored by count (limit ${limits.discolored}%).`, action: 'Input concern: PNS defines discoloration as caused by heating. Review drying and storage.', source: 'pns_reference_count' });
    if (broken! > limits.broken) {
      const severe = broken! > t.severeBrokenCountPct;
      const explanation = `${fmt(broken!)} broken by count (limit ${limits.broken}%)${severe ? `; above the ${t.severeBrokenCountPct}% severe level` : ''}.`;
      if (isRetest) add({ rule: 'R5', outcome: 'qa_review', severe, title: 'Broken grains above limit on retest', explanation, action: 'The paddy may already be cracked or fissured. Inspect the paddy before further adjustment.', source: 'pns_reference_count' });
      else add({ rule: 'R7', outcome: 'adjust_retest', severe, title: 'Broken grains above limit', explanation, action: 'Review whitening/polishing intensity, rubber-roll husking, and feed rate, then retest.', source: 'pns_reference_count' });
    }
  }

  // R10 — within ±2 percentage points of any limit. A flat ±2 band around the 1% discolored
  // limit would include 0%, so R11 could never fire; the band is capped at half the limit.
  const band = (limit: number) => Math.min(t.nearLimitPoints, limit / 2);
  const near: [string, number | null, number[]][] = [
    ['Total recovery', recovery, [t.recoveryVerifyBelow, t.recoveryTarget]],
    ['Head rice share of milled rice', headShare, [t.minHeadShareOfMilled]],
    ['Broken (count)', broken, [limits.broken]],
    ['Chalky (count)', chalky, [limits.chalky]],
    ['Discolored (count)', discolored, [limits.discolored]],
  ];
  for (const [name, value, bounds] of near) {
    if (value === null) continue;
    const close = bounds.filter(b => Math.abs(value - b) <= band(b));
    if (close.length) add({ rule: 'R10', outcome: 'adjust_retest', title: `${name} close to a limit`, explanation: `${name} is ${fmt(value)}, within ${close.map(b => `±${Number(band(b).toFixed(2))} points of ${fmt(b)}`).join(' and ')}.`, action: 'Take another sample before deciding.', source: 'project_set' });
  }

  if (!findings.length) add({ rule: 'R11', outcome: 'proceed', title: 'No rule triggered', explanation: 'All evaluated checks are within their limits.', action: 'Proceed to full-scale milling.', source: 'project_set' });
  findings.sort((a, b) => RANK[b.outcome] - RANK[a.outcome] || Number(a.rule.slice(1)) - Number(b.rule.slice(1)));
  const blocked = findings.some(f => f.rule === 'R1' && f.source === 'measured_weights') || !screening;
  return {
    outcome: findings[0].outcome, blocked, findings, notEvaluated, isRetest,
    metrics: { totalRecovery: recovery, headShareOfMilled: headShare, brokenCountPct: broken, chalkyCountPct: chalky, discoloredCountPct: discolored, uncertainPct, grains },
  };
}
