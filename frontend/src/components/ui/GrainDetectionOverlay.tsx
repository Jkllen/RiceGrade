import { useState } from 'react';
import type { ScreeningResult } from '../../lib/evaluations';

const COLOR: Record<string, string> = {
  whole_grain: '#32c97e',
  broken_grain: '#ffc44d',
  chalky_grain: '#61b7ff',
  discolored_grain: '#ff668a',
};
const LABEL: Record<string, string> = {
  whole_grain: 'Whole',
  broken_grain: 'Broken',
  chalky_grain: 'Chalky',
  discolored_grain: 'Discolored',
};

/** Draws the model's detected regions, not ground-truth annotations. */
export function GrainDetectionOverlay({ imageUrl, result }: {imageUrl: string; result: ScreeningResult}) {
  const [natural, setNatural] = useState<{ width: number; height: number } | null>(null);
  const [showBoxes, setShowBoxes] = useState(true);
  const [showLabels, setShowLabels] = useState(true);
  const imageWidth = result.image_width || natural?.width || 0;
  const imageHeight = result.image_height || natural?.height || 0;
  const hasCoords = imageWidth > 0 && imageHeight > 0;
  return <section className="grain-inspection" aria-label="Visual inspection of rice-grain detection">
    <div className="grain-inspection-heading">
      <div><strong>Detection inspection</strong><p>Colored boundaries show what OpenCV isolated; labels show the provisional XGBoost prediction.</p></div>
      <div className="grain-inspection-toggles">
        <label><input type="checkbox" checked={showBoxes} onChange={e => setShowBoxes(e.target.checked)}/> Show boundaries</label>
        <label><input type="checkbox" checked={showLabels} onChange={e => setShowLabels(e.target.checked)}/> Show numbers</label>
      </div>
    </div>
    <div className="grain-inspection-image">
      <img src={imageUrl} alt="Rice photograph annotated with experimental detected regions" onLoad={e => setNatural({width:e.currentTarget.naturalWidth,height:e.currentTarget.naturalHeight})}/>
      {hasCoords && <svg className="grain-overlay-svg" viewBox={`0 0 ${imageWidth} ${imageHeight}`} preserveAspectRatio="none" aria-label={`Predicted locations for ${result.grains.length} detected regions`}>
        {result.grains.map((grain, index) => {
          const [x, y, w, h] = grain.bbox_xywh;
          const color = COLOR[grain.category] || '#eeeeee';
          const validBox = [x,y,w,h].every(Number.isFinite) && w > 0 && h > 0;
          if (!validBox) return null;
          const validOutline = (grain.outline_xy?.length ?? 0) >= 3;
          const labelHeight = Math.max(14, imageHeight / 55);
          const labelWidth = Math.max(24, imageWidth / 26);
          return <g key={`${grain.grain_index}-${index}`}>
            <title>{`${grain.grain_index + 1}: ${LABEL[grain.category] || grain.category} (${(grain.score * 100).toFixed(1)}% uncalibrated score)`}</title>
            {showBoxes && validOutline ? <polygon points={grain.outline_xy!.map(([px,py])=>`${px},${py}`).join(' ')} fill={color} fillOpacity="0.12" stroke={color} strokeWidth={Math.max(1.4,imageWidth/400)} vectorEffect="non-scaling-stroke" /> : null}
            {showBoxes && <rect x={x} y={y} width={w} height={h} stroke={color} strokeWidth={Math.max(1.3,imageWidth/500)} fill="none" vectorEffect="non-scaling-stroke" strokeDasharray={validOutline ? '4 3' : undefined} />}
            {showLabels && <g>
              <rect x={x} y={Math.max(0, y - labelHeight)} width={labelWidth} height={labelHeight} fill={color} rx="2" />
              <text x={x + labelWidth / 2} y={Math.max(0, y - labelHeight) + labelHeight * 0.75} fill="#081a13" textAnchor="middle" fontSize={labelHeight * 0.72} fontWeight="bold">{grain.grain_index + 1}</text>
            </g>}
          </g>;
        })}
      </svg>}
    </div>
    <div className="grain-class-legend">
      {Object.entries(LABEL).map(([category, label]) => <span key={category}><i style={{backgroundColor:COLOR[category]}}/>{label}</span>)}
    </div>
    <details className="grain-region-details">
      <summary>Inspect individual region predictions ({result.grains.length})</summary>
      <div className="grain-region-scroll"><table>
        <thead><tr><th scope="col">#</th><th scope="col">Predicted class</th><th scope="col">Score*</th><th scope="col">Region (x, y, w, h)</th></tr></thead>
        <tbody>{result.grains.map((grain,index)=><tr key={`${grain.grain_index}-${index}`}>
          <td>{grain.grain_index+1}</td><td><span className="grain-region-class"><i style={{backgroundColor:COLOR[grain.category]}}/>{LABEL[grain.category]||grain.category}</span></td>
          <td>{(grain.score*100).toFixed(1)}%</td><td>{grain.bbox_xywh.map(Math.round).join(', ')}</td>
        </tr>)}</tbody>
      </table></div><p className="muted">*Scores are uncalibrated model outputs, not validated confidence probabilities.</p>
    </details>
    <p className="muted grain-inspection-note">Boxes show candidate regions, not verified rice grains. Colored outlines are shown when provided by the model server. Inspect false detections, split grains, merged grains, and incorrect class labels before interpreting the counts.</p>
    {!result.image_width && <p className="sample-photo-error">This is an older result without processed-image dimensions. On large or rotated photos, boundaries may not align exactly. Rerun after the backend and model-service updates.</p>}
  </section>;
}
