import { useEffect, useState, type FormEvent, type ChangeEvent } from 'react';
import { Header, Icon, Notice } from '../../../components/ui/Elements';
import { AssessmentInsights } from '../../../components/ui/AssessmentInsights';
import { SamplePhotoInput } from '../../../components/ui/SamplePhotoInput';
import { apiRequest } from '../../../lib/authApi';
import { type Evaluation, type EvaluationInput, type ScreeningRecord, percent } from '../../../lib/evaluations';

const today = () => { const date=new Date();date.setMinutes(date.getMinutes()-date.getTimezoneOffset());return date.toISOString().slice(0,10); };
const blank = ():EvaluationInput=>({lot_id:'',test_run_id:'',test_date:today(),paddy_input_weight:0,total_milled_rice_weight:0,brown_rice_weight:null,head_rice_weight:null,moisture_content:null,machine_notes:''});
type Props={onCreated:()=>void;onOpenAssessment:(id:number)=>void};
export function AnalysisPage({onCreated,onOpenAssessment}:Props){
  const [form,setForm]=useState<EvaluationInput>(blank);
  const [image,setImage]=useState<File|null>(null);
  const [preview,setPreview]=useState('');
  const [saved,setSaved]=useState<Evaluation|null>(null);
  const [screening,setScreening]=useState<ScreeningRecord|null>(null);
  const [error,setError]=useState('');
  const [busy,setBusy]=useState(false);
  const [stage,setStage]=useState('');
  useEffect(()=>{if(!image){setPreview('');return;}const url=URL.createObjectURL(image);setPreview(url);return()=>URL.revokeObjectURL(url);},[image]);
  const update=(key:keyof EvaluationInput,value:string|number|null)=>setForm(previous=>({...previous,[key]:value}));
  const numeric=(key:keyof EvaluationInput,required=false)=>(event:ChangeEvent<HTMLInputElement>)=>{const raw=event.target.value;update(key,raw===''?(required?0:null):Number(raw));};
  async function submit(event:FormEvent){
    event.preventDefault();setError('');
    if(!image){setError('Add a rice sample photo before selecting Analyze Grain Screen.');return;}
    if(form.total_milled_rice_weight>form.paddy_input_weight){setError('Total milled rice cannot weigh more than the original paddy input.');return;}
    if(form.head_rice_weight!==null&&form.head_rice_weight>form.total_milled_rice_weight){setError('Head rice must not exceed total milled rice weight.');return;}
    if(form.brown_rice_weight!==null&&form.brown_rice_weight<form.total_milled_rice_weight){setError('Brown rice must not weigh less than the milled rice output.');return;}
    setBusy(true);
    let result:Evaluation;
    try{
      setStage('Saving your test-run measurements…');
      result=await apiRequest<Evaluation>('/evaluations',{method:'POST',body:JSON.stringify(form)});
      setSaved(result);onCreated();
    }catch(err){setError(err instanceof Error?err.message:'Unable to create assessment');setBusy(false);return;}
    try{
      setStage('Uploading the sample image…');
      const payload=new FormData();payload.append('image',image);
      await apiRequest(`/evaluations/${result.id}/image`,{method:'POST',body:payload});
      setSaved({...result,has_image:true});
    }catch(err){setError(`Assessment saved, but the photo upload failed: ${err instanceof Error?err.message:'Upload error'}. Open the record to attach another photo.`);setBusy(false);setStage('');return;}
    try{
      setStage('Analyzing grain regions and building insights…');
      const record=await apiRequest<ScreeningRecord>(`/evaluations/${result.id}/screening`,{method:'POST'});
      setScreening(record);onCreated();
    }catch(err){
      setError(`Your assessment was saved, but image analysis could not finish: ${err instanceof Error?err.message:'Service error'}. You can inspect the record and choose whether to retry.`);
      try{setScreening(await apiRequest<ScreeningRecord>(`/evaluations/${result.id}/screening`));}catch{/* details remain accessible */}
    }finally{setBusy(false);setStage('');}
  }
  function reset(){setSaved(null);setScreening(null);setImage(null);setForm(blank());setError('');}
  if(saved)return <><Header eyebrow="TEST-MILL RESULTS" title="Assessment results" description={`${saved.lot_id} · ${saved.test_run_id}`}/>
    {busy&&<Notice><strong>{stage}</strong> Keep this page open until analysis completes.</Notice>}
    {error&&<Notice tone="warning">{error}</Notice>}
    {!busy&&screening?.status==='research_preview'&&screening.result&&<AssessmentInsights evaluation={saved} result={screening.result} imageUrl={preview}/>}
    {!busy&&!(screening?.status==='research_preview'&&screening.result)&&<AssessmentInsights evaluation={saved} result={null} imageUrl={preview}/>}
    <div className="button-row analysis-result-actions"><button type="button" className="button button-primary" onClick={reset}><Icon name="analysis" size={17}/> New assessment</button><button type="button" className="button button-secondary" onClick={()=>onOpenAssessment(saved.id)}>View saved record <Icon name="arrow" size={16}/></button></div>
  </>;
  return <><Header eyebrow="ANALYSIS WORKSPACE" title="Test-mill evaluation" description="Enter the test-run measurements, add a sample image, then analyze the grains in one step."/>
    <form className="evaluation-form" onSubmit={submit}>
      <section className="panel form-section"><div className="form-section-title"><span className="step-number">01</span><div><h2>Test-run information</h2><p>Identify the rice lot and its milling run.</p></div></div><div className="form-grid"><label className="field">Lot ID <span className="required">*</span><input required maxLength={80} value={form.lot_id} onChange={e=>update('lot_id',e.target.value)} placeholder="e.g. LOT-2026-001"/></label><label className="field">Test-run ID <span className="required">*</span><input required maxLength={80} value={form.test_run_id} onChange={e=>update('test_run_id',e.target.value)} placeholder="e.g. RUN-001"/></label><label className="field">Test date <span className="required">*</span><input type="date" required value={form.test_date} onChange={e=>update('test_date',e.target.value)}/></label></div></section>
      <section className="panel form-section"><div className="form-section-title"><span className="step-number">02</span><div><h2>Physical measurements</h2><p>Enter values measured during this test run, in grams (g).</p></div></div><div className="form-grid"><label className="field">Original paddy input (g) <span className="required">*</span><input type="number" step="any" min="0.001" required value={form.paddy_input_weight||''} onChange={numeric('paddy_input_weight',true)} placeholder="e.g. 1000"/><small>Weight before milling.</small></label><label className="field">Total milled rice output (g) <span className="required">*</span><input type="number" step="any" min="0.001" required value={form.total_milled_rice_weight||''} onChange={numeric('total_milled_rice_weight',true)} placeholder="e.g. 650"/><small>Includes whole and broken milled rice.</small></label><label className="field">Brown rice weight (g) <span className="optional">Optional</span><input type="number" step="any" min="0.001" value={form.brown_rice_weight??''} onChange={numeric('brown_rice_weight')} placeholder="If separately measured"/></label><label className="field">Head rice weight (g) <span className="optional">Optional</span><input type="number" step="any" min="0.001" value={form.head_rice_weight??''} onChange={numeric('head_rice_weight')} placeholder="If separately measured"/></label><label className="field">Measured paddy moisture (%) <span className="optional">Optional</span><input type="number" step="any" min="0.001" max="100" value={form.moisture_content??''} onChange={numeric('moisture_content')} placeholder="If measured by a meter"/></label></div>
        <div className="preview-recovery"><span>Live recovery preview</span><div><div><small>Total recovery</small><strong>{form.paddy_input_weight>0&&form.total_milled_rice_weight>0?percent(form.total_milled_rice_weight/form.paddy_input_weight*100):'—'}</strong></div><div><small>Brown recovery</small><strong>{form.paddy_input_weight>0&&form.brown_rice_weight?percent(form.brown_rice_weight/form.paddy_input_weight*100):'—'}</strong></div><div><small>Head recovery</small><strong>{form.paddy_input_weight>0&&form.head_rice_weight?percent(form.head_rice_weight/form.paddy_input_weight*100):'—'}</strong></div></div><p>The application checks these values again when the assessment is submitted.</p></div>
      </section>
      <section className="panel form-section"><div className="form-section-title"><span className="step-number">03</span><div><h2>Sample image</h2><p>Use a dark, uniform background with separated rice grains and even lighting.</p></div></div><SamplePhotoInput disabled={busy} onPhoto={setImage} title={image?`Selected: ${image.name}`:'Add a photo from your phone or computer'}/>{preview&&<div className="image-preview"><img src={preview} alt="Selected rice sample preview"/><button className="text-button" type="button" onClick={()=>setImage(null)}>Remove photo</button></div>}
        <label className="field notes-field">Machine / sample notes <span className="optional">Optional</span><textarea rows={3} maxLength={2000} value={form.machine_notes} onChange={e=>update('machine_notes',e.target.value)} placeholder="Relevant machine settings or lot observations"/></label></section>
      {error&&<Notice tone="warning">{error}</Notice>}
      <div className="form-actions"><div><strong>Ready to analyze?</strong><p>The system saves your assessment and photo, then opens the grain analysis results automatically.</p></div><button type="submit" className="button button-primary" disabled={busy||!image}>{busy?stage:'Analyze Grain Screen'} <Icon name="arrow" size={18}/></button></div>
    </form>
  </>;
}
