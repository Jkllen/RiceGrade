import { useEffect, useState } from 'react';
import { Header, Notice, Busy, Empty, Icon, StatusPill } from '../../../components/ui/Elements';
import { AssessmentInsights } from '../../../components/ui/AssessmentInsights';
import { apiRequest, getProtectedImage } from '../../../lib/authApi';
import { type Evaluation, type ScreeningRecord, dateDisplay, percent } from '../../../lib/evaluations';

type Props={onHistory:(id?:number)=>void;onNew:()=>void;refresh:number};
export function ReportsPage({onHistory,onNew,refresh}:Props){
  const [items,setItems]=useState<Evaluation[]>([]);
  const [loading,setLoading]=useState(true);
  const [error,setError]=useState('');
  const [previewId,setPreviewId]=useState<number|null>(null);
  const [screening,setScreening]=useState<ScreeningRecord|null>(null);
  const [imageUrl,setImageUrl]=useState('');
  useEffect(()=>{let live=true;setLoading(true);apiRequest<Evaluation[]>('/evaluations').then(rows=>{if(live){setItems(rows);setError('')}}).catch(e=>{if(live)setError(e.message)}).finally(()=>{if(live)setLoading(false)});return()=>{live=false};},[refresh]);
  const preview=items.find(i=>i.id===previewId);
  useEffect(()=>{let live=true;setScreening(null);if(previewId!==null){apiRequest<ScreeningRecord>(`/evaluations/${previewId}/screening`).then(r=>{if(live)setScreening(r)}).catch(()=>{});}return()=>{live=false};},[previewId,refresh]);
  useEffect(()=>{let live=true;let objectUrl='';setImageUrl('');if(preview?.has_image){getProtectedImage(preview.id).then(url=>{if(live){objectUrl=url;setImageUrl(url)}else URL.revokeObjectURL(url)}).catch(()=>{});}return()=>{live=false;if(objectUrl)URL.revokeObjectURL(objectUrl);};},[preview?.id,preview?.has_image]);
  if(preview)return <><Header eyebrow="EVALUATION REPORT" title={`${preview.lot_id} · ${preview.test_run_id}`} description={`Test-mill evaluation for ${dateDisplay(preview.test_date)}`}/><section className="panel detail-panel"><button className="text-button back-link" onClick={()=>setPreviewId(null)}>← Back to reports</button><AssessmentInsights evaluation={preview} result={screening?.status==='research_preview'?screening.result:null} imageUrl={imageUrl||undefined}/><div className="button-row"><button className="button button-secondary" onClick={()=>onHistory(preview.id)}>Open full assessment</button></div></section></>;
  return <><Header eyebrow="EVALUATION RESULTS" title="Evaluation reports" description="Review saved test-mill measurements, annotated images and decision-support insights."/>{error&&<Notice tone="warning">{error}</Notice>}
    <section className="panel reports-panel"><div className="section-header"><div><h2>Assessment reports</h2><p>Choose a test run to review its saved results.</p></div></div>{loading?<Busy/>:items.length?<div className="record-list">{items.map(i=><button className="record-row" key={i.id} onClick={()=>setPreviewId(i.id)}><div className="record-badge"><Icon name="reports"/></div><div className="record-main"><strong>{i.lot_id} <span className="subtle">/ {i.test_run_id}</span></strong><span>{dateDisplay(i.test_date)} · Total recovery {percent(i.total_milling_recovery)}</span></div><StatusPill>{i.status==='screening_trial'?'Analyzed':'Saved'}</StatusPill><Icon name="arrow" size={18}/></button>)}</div>:<Empty icon="reports" title="No assessments yet" description="Your saved evaluations and their insights will appear here."><button className="button button-primary" onClick={onNew}>New evaluation</button></Empty>}</section>
  </>;
}
