import { useEffect, useState, type FormEvent, type ChangeEvent } from 'react';
import { Header, Icon, Notice } from '../../../components/ui/Elements';
import { apiRequest } from '../../../lib/authApi';
import { type Evaluation, type EvaluationInput, percent } from '../../../lib/evaluations';

const today = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
const blank = (): EvaluationInput => ({ lot_id:'', test_run_id:'', test_date:today(), paddy_input_weight:0, total_milled_rice_weight:0, brown_rice_weight:null, head_rice_weight:null, moisture_content:null, machine_notes:'' });
type Props = { onCreated: () => void; onHistory: () => void };
export function AnalysisPage({ onCreated, onHistory }: Props) {
  const [form, setForm] = useState<EvaluationInput>(blank);
  const [image, setImage] = useState<File | null>(null);
  const [preview, setPreview] = useState('');
  const [saved, setSaved] = useState<Evaluation | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  useEffect(() => { if (!image) { setPreview(''); return; } const url=URL.createObjectURL(image); setPreview(url); return () => URL.revokeObjectURL(url); }, [image]);
  const update = (key: keyof EvaluationInput, value: string | number | null) => setForm(previous => ({...previous, [key]: value}));
  const numeric = (key: keyof EvaluationInput, required = false) => (event: ChangeEvent<HTMLInputElement>) => { const raw = event.target.value; update(key, raw === '' ? (required ? 0 : null) : Number(raw)); };
  async function submit(event: FormEvent) {
    event.preventDefault(); setError(''); setNotice('');
    if (form.total_milled_rice_weight > form.paddy_input_weight) { setError('Total milled rice cannot weigh more than the original paddy input.'); return; }
    if (form.head_rice_weight !== null && form.head_rice_weight > form.total_milled_rice_weight) { setError('Head rice must not exceed total milled rice weight.'); return; }
    if (form.brown_rice_weight !== null && form.brown_rice_weight < form.total_milled_rice_weight) { setError('Brown rice must not weigh less than the final milled rice output.'); return; }
    setBusy(true);
    try {
      const result = await apiRequest<Evaluation>('/evaluations', {method:'POST', body:JSON.stringify(form)});
      setSaved(result);
      if (image) {
        const upload = new FormData(); upload.append('image', image);
        try { await apiRequest(`/evaluations/${result.id}/image`, {method:'POST', body:upload}); setSaved({...result,has_image:true}); }
        catch (err) { setNotice(`Measurements saved, but image upload failed: ${err instanceof Error ? err.message : 'Upload error'}. You can upload it again from the assessment details.`); }
      }
      onCreated();
    } catch (err) { setError(err instanceof Error ? err.message : 'Unable to save the assessment'); }
    finally { setBusy(false); }
  }
  if (saved) return <><Header eyebrow="TEST-MILL EVALUATION" title="Assessment saved" description="Your measurements have been securely stored in your account."/><div className="panel success-panel"><div className="large-success"><Icon name="check" size={28}/></div><h2>{saved.lot_id} · {saved.test_run_id}</h2><p>Physical milling-recovery values have been calculated. Automated grain classification and DSS reporting will be available when the validated model pipeline is integrated.</p><div className="result-grid"><div><span>Total milling recovery</span><strong>{percent(saved.total_milling_recovery)}</strong></div><div><span>Brown-rice recovery</span><strong>{percent(saved.brown_rice_recovery)}</strong></div><div><span>Head-rice recovery</span><strong>{percent(saved.head_rice_recovery)}</strong></div></div>{notice && <Notice tone="warning">{notice}</Notice>}<Notice>Assessment status: <strong>Awaiting integration integration</strong>. These recovery percentages are calculated from your entered physical weights, not image predictions.</Notice><div className="button-row"><button className="button button-primary" onClick={() => {setSaved(null);setImage(null);setForm(blank());setNotice('');}}>Start another test run <Icon name="arrow" size={17}/></button><button className="button button-secondary" onClick={onHistory}>View assessment history</button></div></div></>;
  return <><Header eyebrow="ANALYSIS WORKSPACE" title="New test-mill evaluation" description="Record measurements from one physical test-milling run, then attach the standardized sample photograph."/>
    <Notice><strong>Measurements are real; visual inference is not yet connected.</strong> This form saves your test run and computes recovery. The trained hybrid classifier is available, but automatic grain isolation and live analysis are not yet connected. No results are simulated.</Notice>
    <form className="evaluation-form" onSubmit={submit}>
      <section className="panel form-section"><div className="form-section-title"><span className="step-number">01</span><div><h2>Test-run information</h2><p>Identify the paddy lot and this specific test milling.</p></div></div><div className="form-grid"><label className="field">Lot ID <span className="required">*</span><input required maxLength={80} value={form.lot_id} onChange={e => update('lot_id',e.target.value)} placeholder="e.g. LOT-2026-001"/></label><label className="field">Test-run ID <span className="required">*</span><input required maxLength={80} value={form.test_run_id} onChange={e => update('test_run_id',e.target.value)} placeholder="e.g. RUN-001"/></label><label className="field">Test date <span className="required">*</span><input type="date" required value={form.test_date} onChange={e => update('test_date',e.target.value)}/></label></div></section>
      <section className="panel form-section"><div className="form-section-title"><span className="step-number">02</span><div><h2>Physical measurements</h2><p>Enter mass measurements from the same test run, in grams (g).</p></div></div><div className="form-grid"><label className="field">Original paddy input (g) <span className="required">*</span><input type="number" step="any" min="0.001" required value={form.paddy_input_weight || ''} onChange={numeric('paddy_input_weight',true)} placeholder="e.g. 1000"/><small>Measured before test milling.</small></label><label className="field">Total milled rice output (g) <span className="required">*</span><input type="number" step="any" min="0.001" required value={form.total_milled_rice_weight || ''} onChange={numeric('total_milled_rice_weight',true)} placeholder="e.g. 650"/><small>White milled rice output, whole + broken.</small></label><label className="field">Brown rice weight (g) <span className="optional">Optional</span><input type="number" step="any" min="0.001" value={form.brown_rice_weight ?? ''} onChange={numeric('brown_rice_weight')} placeholder="If separately measured"/></label><label className="field">Head rice weight (g) <span className="optional">Optional</span><input type="number" step="any" min="0.001" value={form.head_rice_weight ?? ''} onChange={numeric('head_rice_weight')} placeholder="If separately measured"/></label><label className="field">Measured paddy moisture (%) <span className="optional">Optional</span><input type="number" step="any" min="0.001" max="100" value={form.moisture_content ?? ''} onChange={numeric('moisture_content')} placeholder="If measured by a meter"/></label></div>
        <div className="preview-recovery"><span>Live recovery preview</span><div><div><small>Total recovery</small><strong>{form.paddy_input_weight > 0 && form.total_milled_rice_weight > 0 ? percent(form.total_milled_rice_weight/form.paddy_input_weight*100) : '—'}</strong></div><div><small>Brown recovery</small><strong>{form.paddy_input_weight > 0 && form.brown_rice_weight ? percent(form.brown_rice_weight/form.paddy_input_weight*100) : '—'}</strong></div><div><small>Head recovery</small><strong>{form.paddy_input_weight > 0 && form.head_rice_weight ? percent(form.head_rice_weight/form.paddy_input_weight*100) : '—'}</strong></div></div><p>Preview only. The backend independently validates and recalculates these values when you save.</p></div>
      </section>
      <section className="panel form-section"><div className="form-section-title"><span className="step-number">03</span><div><h2>Sample image</h2><p>Photograph the test-milled white rice on a uniform background under consistent lighting.</p></div></div><label className="upload-zone"><input type="file" accept="image/png,image/jpeg,image/webp" onChange={e => {const file=e.target.files?.[0]??null;setImage(file);}}/><span className="upload-icon"><Icon name="photo" size={25}/></span><strong>{image ? image.name : 'Choose a rice sample photo'}</strong><span>JPEG, PNG, or WebP · up to 5 MB · optional for now</span></label>{preview && <div className="image-preview"><img src={preview} alt="Selected rice sample preview"/><button className="text-button" type="button" onClick={() => setImage(null)}>Remove image</button></div>}
        <label className="field notes-field">Optional machine / sample notes<textarea rows={3} maxLength={2000} value={form.machine_notes} onChange={e => update('machine_notes',e.target.value)} placeholder="Equipment or lot context; do not include passwords or confidential details."/></label></section>
      {error && <Notice tone="warning">{error}</Notice>}
      <div className="form-actions"><div><strong>Ready to save?</strong><p>No classification or DSS output will be generated yet.</p></div><button type="submit" className="button button-primary" disabled={busy}>{busy ? 'Saving assessment…' : 'Save test-mill assessment'} <Icon name="arrow" size={18}/></button></div>
    </form></>;
}
