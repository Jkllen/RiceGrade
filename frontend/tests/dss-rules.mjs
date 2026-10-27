// Run: npm run test:dss — boundary tests for the deterministic DSS rules (R1–R11, no R9).
import assert from 'node:assert/strict';
const { evaluateDss, isRetestOf } = await import('./.dss-built/dss.js');

const evaluation = (over = {}) => ({
  id: 1, user_id: 1, lot_id: 'LOT-1', test_run_id: 'RUN-1', test_date: '2026-10-01', paddy_input_weight: 1000,
  total_milled_rice_weight: 680, brown_rice_weight: null, head_rice_weight: 500, moisture_content: null,
  machine_notes: '', total_milling_recovery: 68, brown_rice_recovery: null, head_rice_recovery: 50,
  status: 'screening_trial', created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z', has_image: true, ...over,
});
// 200 grains by default: counts are converted to count percentages by the rules engine.
const screening = ({ broken = 10, chalky = 4, discolored = 0, total = 200, uncertain = 0 } = {}) => {
  const whole = total - broken - chalky - discolored;
  const labels = [...Array(broken).fill('broken_grain'), ...Array(chalky).fill('chalky_grain'), ...Array(discolored).fill('discolored_grain'), ...Array(whole).fill('whole_grain')];
  return {
    status: 'experimental_unvalidated_segmentation', total_grains: total,
    counts: { broken_grain: broken, chalky_grain: chalky, discolored_grain: discolored, whole_grain: whole },
    grains: labels.map((category, i) => ({ grain_index: i, category, score: i < uncertain ? 0.59 : 0.6, bbox_xywh: [0, 0, 1, 1] })),
  };
};
const run = (e = {}, s = {}, extra = {}) => evaluateDss({ evaluation: evaluation(e), screening: s === null ? null : screening(s), isRetest: false, ...extra });
const rules = result => result.findings.map(f => f.rule);

// R11 — clean run. Score 0.60 exactly is not uncertain.
let r = run();
assert.equal(r.outcome, 'proceed'); assert.deepEqual(rules(r), ['R11']); assert.equal(r.blocked, false);

// R1 — missing screening, too few grains, >10% uncertain, impossible weights.
r = run({}, null); assert.equal(r.outcome, 'manual_verification'); assert.equal(r.blocked, true); assert.ok(rules(r).includes('R1'));
assert.ok(rules(run({}, { total: 99, broken: 5, chalky: 2 })).includes('R1'));
assert.ok(!rules(run({}, { total: 100, broken: 5, chalky: 2 })).includes('R1'));
assert.ok(!rules(run({}, { uncertain: 20 })).includes('R1'), '10.0% uncertain is not above 10%');
assert.ok(rules(run({}, { uncertain: 21 })).includes('R1'));
r = run({ total_milled_rice_weight: 1100 }); assert.equal(r.blocked, true); assert.equal(r.metrics.totalRecovery, null); assert.ok(r.notEvaluated.some(n => n.startsWith('R2')));
assert.equal(run({ head_rice_weight: 700 }).blocked, true);
assert.equal(run({ brown_rice_weight: 600 }).blocked, true);
assert.equal(run({ paddy_input_weight: 0 }).blocked, true);

// R2 / R6 — recovery boundaries at 62% and 65%; confirmation turns R2 into R6.
assert.ok(rules(run({ total_milled_rice_weight: 619.9 })).includes('R2'));
assert.equal(run({ total_milled_rice_weight: 619.9 }).outcome, 'manual_verification');
r = run({ total_milled_rice_weight: 619.9 }, {}, { recoveryConfirmed: true }); assert.ok(rules(r).includes('R6')); assert.ok(!rules(r).includes('R2'));
assert.ok(rules(run({ total_milled_rice_weight: 620 })).includes('R6'));
assert.ok(rules(run({ total_milled_rice_weight: 649.9 })).includes('R6'));
assert.ok(!rules(run({ total_milled_rice_weight: 650, head_rice_weight: 400 })).includes('R6'), '65% exactly passes');

// R8 — head rice share of MILLED rice, strictly below 50%.
assert.ok(!rules(run({ head_rice_weight: 340 })).includes('R8'), '340/680 = 50%');
assert.ok(rules(run({ head_rice_weight: 339 })).includes('R8'));
assert.ok(run({ head_rice_weight: null }).notEvaluated.some(n => n.startsWith('R8')));

// R3 / R4 — chalky 7%, discolored 1% by count (strictly above).
assert.ok(!rules(run({}, { chalky: 14 })).includes('R3'));
r = run({}, { chalky: 15 }); assert.ok(rules(r).includes('R3')); assert.equal(r.outcome, 'qa_review');
assert.ok(!rules(run({}, { discolored: 2 })).includes('R4'));
assert.ok(rules(run({}, { discolored: 3 })).includes('R4'));

// R7 / R5 — broken 15% by count; retest escalates to QA Review; >45% is severe.
assert.ok(!rules(run({}, { broken: 30 })).includes('R7'));
r = run({}, { broken: 31 }); assert.ok(rules(r).includes('R7')); assert.equal(r.outcome, 'adjust_retest');
r = run({}, { broken: 31 }, { isRetest: true }); assert.ok(rules(r).includes('R5')); assert.ok(!rules(r).includes('R7')); assert.equal(r.outcome, 'qa_review');
assert.equal(run({}, { broken: 90 }).findings.find(f => f.rule === 'R7').severe, false, '45% exactly is not severe');
assert.equal(run({}, { broken: 91 }).findings.find(f => f.rule === 'R7').severe, true);

// No grading and no R9: the result carries no grade, and R9 never appears.
r = run({}, { broken: 40, chalky: 20, discolored: 4 });
assert.equal('targetGrade' in r, false); assert.ok(!rules(r).includes('R9'));

// R10 — within ±2 points of a percentage limit, on either side.
assert.ok(rules(run({ total_milled_rice_weight: 670 })).includes('R10'), '67% is 2 points from 65%');
assert.ok(!rules(run({ total_milled_rice_weight: 671 })).includes('R10'));
assert.ok(rules(run({}, { broken: 26 })).includes('R10'), '13% broken is 2 points from 15%');
assert.ok(!rules(run({}, { broken: 25 })).includes('R10'));
// Limits under 4% use a band of half the limit: discolored 1% → 0.5%–1.5%.
assert.ok(!rules(run({}, { discolored: 0 })).includes('R10'), '0% discolored must still allow Proceed');
assert.ok(rules(run({}, { discolored: 1 })).includes('R10'), '0.5% discolored is 0.5 points from 1%');
assert.ok(rules(run({}, { discolored: 2 })).includes('R10'));

// Multiple warnings: highest outcome wins and findings are ranked.
r = run({ total_milled_rice_weight: 600, head_rice_weight: 200 }, { broken: 40, chalky: 20 });
assert.equal(r.outcome, 'manual_verification'); assert.deepEqual(rules(r).slice(0, 2), ['R2', 'R3']);

// Retest detection: same lot (case/space-insensitive), earlier test.
const first = evaluation({ id: 1, test_date: '2026-10-01' }), second = evaluation({ id: 2, lot_id: ' lot-1 ', test_date: '2026-10-02' });
assert.equal(isRetestOf(second, [first, second]), true);
assert.equal(isRetestOf(first, [first, second]), false);
assert.equal(isRetestOf(evaluation({ id: 3, lot_id: 'LOT-2' }), [first, second]), false);

console.log('DSS rule tests passed');
