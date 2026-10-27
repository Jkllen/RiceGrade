import { useState } from "react";
import {
  DSS_THRESHOLDS,
  OUTCOME_LABELS,
  SOURCE_LABELS,
  VISUAL_LIMITS,
  type DssOutcome,
  evaluateDss,
} from "../../lib/dss";
import {
  type Evaluation,
  type ScreeningResult,
  qualityClassNames,
  percent,
} from "../../lib/evaluations";
import { GrainDetectionOverlay } from "./GrainDetectionOverlay";
import { Busy, Icon, Notice } from "./Elements";

// Reuses the existing card colours: red for verify/QA, amber for retest, green for proceed.
const PRIORITY: Record<DssOutcome, string> = {
  manual_verification: "dss-attention",
  qa_review: "dss-attention",
  adjust_retest: "dss-review",
  proceed: "dss-info",
};

type Props = {
  evaluation: Evaluation;
  result: ScreeningResult | null;
  imageUrl?: string;
  /** An earlier test run of the same lot exists (see isRetestOf). */
  isRetest?: boolean;
  /** Hold the recommendation until the saved screening result has loaded. */
  screeningLoading?: boolean;
};
export function AssessmentInsights({
  evaluation,
  result,
  imageUrl,
  isRetest = false,
  screeningLoading = false,
}: Props) {
  const [recoveryConfirmed, setRecoveryConfirmed] = useState(false);
  const dss = evaluateDss({
    evaluation,
    screening: result,
    isRetest,
    recoveryConfirmed,
  });
  const showConfirm =
    dss.findings.some((f) => f.rule === "R2") || recoveryConfirmed;
  return (
    <div className="assessment-insights">
      <div className="insight-split">
        <section className="insight-image-panel" aria-label="Analyzed sample">
          <div className="insight-panel-heading">
            <div>
              <p className="eyebrow">VISUAL ANALYSIS</p>
              <h3>Grain detection</h3>
            </div>
            {result && (
              <span className="insight-tag">
                {result.total_grains} classified objects
              </span>
            )}
          </div>
          {result && imageUrl ? (
            <GrainDetectionOverlay imageUrl={imageUrl} result={result} />
          ) : imageUrl ? (
            <div className="insight-image-placeholder">
              <img src={imageUrl} alt="Submitted rice sample" />
            </div>
          ) : (
            <div className="insight-image-empty">
              <Icon name="photo" size={27} />
              <p>Attach a sample image to inspect grain classifications.</p>
            </div>
          )}
          {result && (
            <div className="class-grid" aria-label="Grain count distribution">
              {qualityClassNames.map((c) => (
                <div className="class-metric" key={c.id}>
                  <span>{c.title}</span>
                  <strong>{result.counts[c.id] ?? 0}</strong>
                  <small>
                    {Number(result.count_percentages[c.id] ?? 0).toFixed(1)}% by
                    count
                  </small>
                </div>
              ))}
            </div>
          )}
          {result && (
            <p className="measurement-footnote">
              Image percentages use detected grain counts, not measured grain
              weights.
            </p>
          )}
        </section>
        <aside
          className="insight-dss-panel"
          aria-label="Decision support recommendation"
        >
          <div className="insight-panel-heading">
            <div>
              <p className="eyebrow">DECISION SUPPORT</p>
              <h3>Recommendation</h3>
            </div>
            <span className="insight-icon">
              <Icon name="chart" size={19} />
            </span>
          </div>
          {screeningLoading ? (
            <Busy label="Loading screening result…" />
          ) : (
            <>
              <div className={`dss-outcome dss-outcome-${dss.outcome}`}>
                <span>Outcome</span>
                <strong>
                  {dss.blocked
                    ? "Blocked: Manual Verification"
                    : OUTCOME_LABELS[dss.outcome]}
                </strong>
                {dss.isRetest && <small>Retest of lot {evaluation.lot_id}</small>}
              </div>
              {dss.blocked && (
                <Notice tone="warning">
                  <strong>Normal assessment is blocked.</strong> Required inputs
                  are missing or impossible. Resolve the R1 items before reading
                  this as a milling decision.
                </Notice>
              )}
              <div className="dss-metrics">
                <div>
                  <span>Total recovery</span>
                  <strong>{percent(dss.metrics.totalRecovery)}</strong>
                  <small>
                    Verify below {DSS_THRESHOLDS.recoveryVerifyBelow}% · target{" "}
                    {DSS_THRESHOLDS.recoveryTarget}%
                  </small>
                </div>
                <div>
                  <span>Head rice of milled</span>
                  <strong>{percent(dss.metrics.headShareOfMilled)}</strong>
                  <small>
                    {dss.metrics.headShareOfMilled == null
                      ? "Not entered"
                      : `Minimum ${DSS_THRESHOLDS.minHeadShareOfMilled}%`}
                  </small>
                </div>
              </div>
              <p className="dss-limits">
                Grain-count limits: broken {VISUAL_LIMITS.broken}% (severe above{" "}
                {DSS_THRESHOLDS.severeBrokenCountPct}%), chalky{" "}
                {VISUAL_LIMITS.chalky}%, discolored {VISUAL_LIMITS.discolored}%.
              </p>
              {showConfirm && (
                <label className="dss-confirm">
                  <input
                    type="checkbox"
                    checked={recoveryConfirmed}
                    onChange={(e) => setRecoveryConfirmed(e.target.checked)}
                  />
                  Weights and test-milling procedure re-checked; low recovery is
                  confirmed (R2 → R6). Not saved.
                </label>
              )}
              <div className="dss-list">
                {dss.findings.map((f, i) => (
                  <article
                    key={`${f.rule}-${i}`}
                    className={`dss-item ${PRIORITY[f.outcome]}`}
                  >
                    <div className="dss-item-title">
                      <span className="dss-number">{f.rule}</span>
                      <strong>{f.title}</strong>
                    </div>
                    <div className="dss-tags">
                      <span className="insight-tag">
                        {OUTCOME_LABELS[f.outcome]}
                      </span>
                      {f.severe && (
                        <span className="insight-tag dss-severe">Severe</span>
                      )}
                    </div>
                    <p className="dss-observation">{f.explanation}</p>
                    <p className="dss-action">
                      <b>Suggested action</b> {f.action}
                    </p>
                    <small>{SOURCE_LABELS[f.source]}</small>
                  </article>
                ))}
              </div>
              {dss.notEvaluated.length > 0 && (
                <div className="dss-skipped">
                  <strong>Not evaluated</strong>
                  <ul>
                    {dss.notEvaluated.map((n) => (
                      <li key={n}>{n}</li>
                    ))}
                  </ul>
                </div>
              )}
              <p className="dss-footnote">
                Image percentages are by grain count, not weight. Final
                equipment adjustments remain the operator's decision.
              </p>
            </>
          )}
        </aside>
      </div>
    </div>
  );
}
