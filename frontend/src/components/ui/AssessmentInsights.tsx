import {
  buildDecisionSupport,
  TOTAL_RECOVERY_REFERENCE,
  HEAD_RECOVERY_REFERENCE,
} from "../../lib/decisionSupport";
import {
  type Evaluation,
  type ScreeningResult,
  qualityClassNames,
  percent,
} from "../../lib/evaluations";
import { GrainDetectionOverlay } from "./GrainDetectionOverlay";
import { Icon } from "./Elements";

type Props = {
  evaluation: Evaluation;
  result: ScreeningResult | null;
  imageUrl?: string;
};
export function AssessmentInsights({ evaluation, result, imageUrl }: Props) {
  const items = buildDecisionSupport(evaluation, result);
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
          aria-label="Decision support findings"
        >
          <div className="insight-panel-heading">
            <div>
              <p className="eyebrow">DECISION SUPPORT</p>
              <h3>Assessment insights</h3>
            </div>
            <span className="insight-icon">
              <Icon name="chart" size={19} />
            </span>
          </div>
          <p className="dss-intro">
            Recommendations based on recorded recovery measurements
            {result ? " and image observations" : ""}.
          </p>
          <div className="dss-metrics">
            <div>
              <span>Total recovery</span>
              <strong>{percent(evaluation.total_milling_recovery)}</strong>
              <small>Reference: {TOTAL_RECOVERY_REFERENCE}%</small>
            </div>
            <div>
              <span>Head recovery</span>
              <strong>{percent(evaluation.head_rice_recovery)}</strong>
              <small>
                {evaluation.head_rice_recovery == null
                  ? "Not entered"
                  : `Reference: ${HEAD_RECOVERY_REFERENCE}%`}
              </small>
            </div>
          </div>
          <div className="dss-list">
            {items.map((item, i) => (
              <article
                key={`${item.title}-${i}`}
                className={`dss-item dss-${item.priority}`}
              >
                <div className="dss-item-title">
                  <span className="dss-number">
                    {String(i + 1).padStart(2, "0")}
                  </span>
                  <strong>{item.title}</strong>
                </div>
                <p className="dss-observation">{item.observation}</p>
                <p className="dss-action">
                  <b>Suggested action</b> {item.action}
                </p>
                <small>{item.source}</small>
              </article>
            ))}
          </div>
          <p className="dss-footnote">
            Reference benchmarks follow{" "}
            <a
              href="https://www.philrice.gov.ph/rice-breeding-operations-manual/"
              target="_blank"
              rel="noopener noreferrer"
            >
              PhilRice breeding operations guidance
            </a>
            ; facility-specific conditions and final equipment adjustments
            remain the operator's decision.
          </p>
        </aside>
      </div>
    </div>
  );
}
