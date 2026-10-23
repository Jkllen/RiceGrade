import { useState } from "react";
import type { ScreeningResult } from "../../lib/evaluations";

const COLOR: Record<string, string> = {
  whole_grain: "#a7c957",
  broken_grain: "#6a994e",
  chalky_grain: "#f2e8cf",
  discolored_grain: "#bc4749",
};
const LABEL: Record<string, string> = {
  whole_grain: "Whole",
  broken_grain: "Broken",
  chalky_grain: "Chalky",
  discolored_grain: "Discolored",
};

/** Predictions and coordinates are drawn directly from the saved API result. */
export function GrainDetectionOverlay({
  imageUrl,
  result,
}: {
  imageUrl: string;
  result: ScreeningResult;
}) {
  const [natural, setNatural] = useState<{
    width: number;
    height: number;
  } | null>(null);
  const [showBoundaries, setShowBoundaries] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const width = result.image_width || natural?.width || 0;
  const height = result.image_height || natural?.height || 0;
  return (
    <section
      className="grain-inspection"
      aria-label="Rice-grain detection and classification"
    >
      <div className="grain-inspection-heading">
        <div>
          <strong>Annotated sample</strong>
          <p>Each outlined grain is labeled with its predicted category.</p>
        </div>
        <div className="grain-inspection-toggles">
          <label>
            <input
              type="checkbox"
              checked={showBoundaries}
              onChange={(e) => setShowBoundaries(e.target.checked)}
            />{" "}
            Outlines
          </label>
          <label>
            <input
              type="checkbox"
              checked={showLabels}
              onChange={(e) => setShowLabels(e.target.checked)}
            />{" "}
            Category labels
          </label>
        </div>
      </div>
      <div className="grain-inspection-image">
        <img
          src={imageUrl}
          alt="Rice sample with grain classification overlay"
          onLoad={(e) =>
            setNatural({
              width: e.currentTarget.naturalWidth,
              height: e.currentTarget.naturalHeight,
            })
          }
        />
        {width > 0 && height > 0 && (
          <svg
            className="grain-overlay-svg"
            viewBox={`0 0 ${width} ${height}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`Overlays for ${result.grains.length} predicted grain regions`}
          >
            {result.grains.map((grain, index) => {
              const [x, y, w, h] = grain.bbox_xywh;
              if (![x, y, w, h].every(Number.isFinite) || w <= 0 || h <= 0)
                return null;
              const className = LABEL[grain.category] || grain.category;
              const color = COLOR[grain.category] || "#f2e8cf";
              const outline = (grain.outline_xy?.length ?? 0) >= 3;
              const fontSize = Math.max(11, Math.min(18, width / 54));
              const labelHeight = fontSize * 1.65;
              const label = `${grain.grain_index + 1} · ${className}`;
              const labelWidth = Math.min(
                width,
                Math.max(46, label.length * fontSize * 0.62 + 14),
              );
              const labelX = Math.min(
                Math.max(0, x),
                Math.max(0, width - labelWidth),
              );
              const labelY =
                y >= labelHeight
                  ? y - labelHeight
                  : Math.min(height - labelHeight, y + h);
              return (
                <g key={`${grain.grain_index}-${index}`}>
                  <title>{`Grain ${grain.grain_index + 1}: ${className}, model score ${(grain.score * 100).toFixed(1)}%`}</title>
                  {showBoundaries && outline && (
                    <polygon
                      points={grain
                        .outline_xy!.map(([px, py]) => `${px},${py}`)
                        .join(" ")}
                      stroke={color}
                      strokeWidth={2}
                      fill={color}
                      fillOpacity={0.09}
                      vectorEffect="non-scaling-stroke"
                    />
                  )}
                  {showBoundaries && (
                    <rect
                      x={x}
                      y={y}
                      width={w}
                      height={h}
                      stroke={color}
                      strokeWidth={1.7}
                      fill="none"
                      vectorEffect="non-scaling-stroke"
                      strokeDasharray={outline ? "4 3" : undefined}
                    />
                  )}
                  {showLabels && (
                    <g>
                      <rect
                        x={labelX}
                        y={Math.max(0, labelY)}
                        width={labelWidth}
                        height={labelHeight}
                        rx={Math.min(5, fontSize * 0.25)}
                        fill={color}
                      />
                      <text
                        x={labelX + labelWidth / 2}
                        y={Math.max(0, labelY) + labelHeight * 0.7}
                        fill={
                          grain.category === "discolored_grain"
                            ? "#ffffff"
                            : "#203527"
                        }
                        textAnchor="middle"
                        fontSize={fontSize}
                        fontWeight="700"
                      >
                        {label}
                      </text>
                    </g>
                  )}
                </g>
              );
            })}
          </svg>
        )}
      </div>
      <div className="grain-class-legend">
        {Object.entries(LABEL).map(([cat, label]) => (
          <span key={cat}>
            <i style={{ backgroundColor: COLOR[cat] }} />
            {label}
          </span>
        ))}
      </div>
      <details className="grain-region-details">
        <summary>Individual grain data ({result.grains.length})</summary>
        <div className="grain-region-scroll">
          <table>
            <thead>
              <tr>
                <th>#</th>
                <th>Class</th>
                <th>Model score</th>
                <th>Location (x, y, w, h)</th>
              </tr>
            </thead>
            <tbody>
              {result.grains.map((grain, i) => (
                <tr key={`${grain.grain_index}-${i}`}>
                  <td>{grain.grain_index + 1}</td>
                  <td>
                    <span className="grain-region-class">
                      <i style={{ backgroundColor: COLOR[grain.category] }} />
                      {LABEL[grain.category] || grain.category}
                    </span>
                  </td>
                  <td>{(grain.score * 100).toFixed(1)}%</td>
                  <td>{grain.bbox_xywh.map(Math.round).join(", ")}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="muted">
          Model scores help inspect predictions; they are not calibrated
          certainty estimates.
        </p>
      </details>
    </section>
  );
}
