// Run: npm run cf:test-api (uses Node 22+ builtin sqlite)
import { DatabaseSync } from 'node:sqlite';
import fs from 'node:fs';
import assert from 'node:assert/strict';
const { onRequest } = await import('./.api-built/[[path]].js');
// Simulate Cloudflare Workers' production PBKDF2 cap, which Node's WebCrypto does not enforce.
const originalDeriveBits = crypto.subtle.deriveBits.bind(crypto.subtle);
crypto.subtle.deriveBits = async (algorithm, ...rest) => {
  if (algorithm?.name === 'PBKDF2' && algorithm.iterations > 100_000) {
    throw new DOMException('PBKDF2 iterations above 100000 are not supported on Cloudflare Workers', 'NotSupportedError');
  }
  return originalDeriveBits(algorithm, ...rest);
};
const sqlite = new DatabaseSync(':memory:');
sqlite.exec(fs.readFileSync(new URL('../migrations/0001_initial.sql',import.meta.url),'utf8'));
sqlite.exec(fs.readFileSync(new URL('../migrations/0002_screening_trials.sql',import.meta.url),'utf8')); 
const d1 = {
  prepare(sql) {
    const q=sqlite.prepare(sql); let params=[];
    return { bind(...values){params=values;return this}, async first(){return q.get(...params)||null},
      async all(){return {results:q.all(...params)}}, async run(){const result=q.run(...params);return {meta:{last_row_id:Number(result.lastInsertRowid),changes:result.changes}}} };
  },
  async batch(statements){const a=[]; for(const statement of statements) a.push(await statement.run());return a;}
};
async function api(method,path,body,auth,otherEnv={}){
  const headers = new Headers();
  if (body && !(body instanceof FormData)) headers.set('Content-Type','application/json');
  if (auth) headers.set('Authorization',`Bearer ${auth}`);
  const req=new Request('https://ricegrade.pages.dev/api'+path,{
    method,headers,body:body instanceof FormData?body:body===undefined?undefined:JSON.stringify(body)
  });
  const res=await onRequest({request:req,env:{DB:d1,...otherEnv}});
  const data= res.status===204?undefined:(path.endsWith('/image') && method==='GET' && res.status===200) ? await res.arrayBuffer():await res.json();
  return {status:res.status,data};
}
let result=await api('GET','/health');assert.equal(result.status,200);
result=await api('POST','/auth/sign-up',{full_name:'Thesis Operator',role:'operator',email:'student@example.org',password:'correct-horse-staple-123'});
assert.equal(result.status,201);assert.equal(result.data.user.role,'operator');const token=result.data.access_token;
result=await api('GET','/auth/me',undefined,token);assert.equal(result.data.email,'student@example.org');
result=await api('POST','/auth/sign-up',{full_name:'Another Person',role:'qa',email:'student@example.org',password:'different-passphrase-123'});assert.equal(result.status,409);
result=await api('POST','/auth/sign-in',{email:'student@example.org',password:'incorrect password'});assert.equal(result.status,401);
result=await api('POST','/auth/sign-in',{email:'student@example.org',password:'correct-horse-staple-123'});assert.equal(result.status,200);const secondary=result.data.access_token;
result=await api('PATCH','/auth/profile',{full_name:'Updated Operator',role:'qa'},token);assert.equal(result.data.full_name,'Updated Operator');
result=await api('POST','/evaluations',{lot_id:'Lot-1',test_run_id:'Run-1',test_date:'2026-10-12',paddy_input_weight:1000,total_milled_rice_weight:670,brown_rice_weight:810,head_rice_weight:480,moisture_content:13,machine_notes:'Test only'},token);
assert.equal(result.status,201);assert.equal(result.data.total_milling_recovery,67);const id=result.data.id;
result=await api('GET','/evaluations',undefined,token);assert.equal(result.data.length,1);assert.equal(result.data[0].has_image,false);
result=await api('GET',`/evaluations/${id}`,undefined,token);assert.equal(result.data.head_rice_recovery,48);
result=await api('POST','/evaluations',{lot_id:'Lot-1',test_run_id:'Run-1',test_date:'2026-10-12',paddy_input_weight:1000,total_milled_rice_weight:670,machine_notes:''},token);assert.equal(result.status,409);
result=await api('POST','/evaluations',{lot_id:'Lot-1',test_run_id:'Run-2',test_date:'2026-10-12',paddy_input_weight:1000,total_milled_rice_weight:1010,machine_notes:''},token);assert.equal(result.status,422);
result=await api('POST','/auth/change-password',{current_password:'correct-horse-staple-123',new_password:'brand-new-long-password-456'},token);assert.equal(result.status,200);
result=await api('GET','/auth/me',undefined,secondary);assert.equal(result.status,401);
result=await api('POST','/auth/sign-in',{email:'student@example.org',password:'brand-new-long-password-456'});assert.equal(result.status,200);
result=await api('POST','/auth/sign-up',{full_name:'Other User',role:'operator',email:'other@example.org',password:'other-super-secret-123'});assert.equal(result.status,201);const other=result.data.access_token;
result=await api('GET',`/evaluations/${id}`,undefined,other);assert.equal(result.status,404);
result=await api('POST',`/evaluations/${id}/image`,undefined,token);assert.equal(result.status,503);
// Simulate R2 after the optional binding is configured.
const store=new Map();const images={
  async put(key,value){store.set(key,value)},
  async get(key){ const buf=store.get(key); return buf?{body:new Blob([buf]).stream()}:null; },
  async delete(key){store.delete(key)}
};
const fakeImage=new File([new Uint8Array([255,216,255,0,0,0,0,0,0,0,0,0,0,0])],'sample.jpg',{type:'image/jpeg'});
const fd=new FormData();fd.append('image',fakeImage);
result=await api('POST',`/evaluations/${id}/image`,fd,token,{IMAGES:images});assert.equal(result.status,200);
result=await api('GET',`/evaluations/${id}/image`,undefined,token,{IMAGES:images});assert.equal(result.status,200);assert.equal(result.data.byteLength,14);
result=await api('GET',`/evaluations/${id}/image`,undefined,other,{IMAGES:images});assert.equal(result.status,404);

// Real model is not run in Node: mock the private HTTPS inference gateway.
result=await api('GET',`/evaluations/${id}/screening`,undefined,token);
assert.equal(result.status,200);assert.equal(result.data.status,'not_requested');
result=await api('POST',`/evaluations/${id}/screening`,undefined,other,{IMAGES:images});assert.equal(result.status,404);
result=await api('POST',`/evaluations/${id}/screening`,undefined,token,{IMAGES:images});assert.equal(result.status,503);
const modelEnv={IMAGES:images,RICEGRADE_ML_ORIGIN:'https://ricegrade-model.example.workers.dev',RICEGRADE_ML_TOKEN:'a'.repeat(64)};
const modelMock=globalThis.fetch;let modelRequests=0;
globalThis.fetch=async (url,opts)=>{
  assert.equal(url,'https://ricegrade-model.example.workers.dev/predict/image');
  assert.equal(opts.headers['X-RiceGrade-Service-Key'],modelEnv.RICEGRADE_ML_TOKEN);
  assert.equal(opts.headers['Content-Type'],'image/jpeg');
  modelRequests++;
  return Response.json({status:'experimental_unvalidated_segmentation',segmentation_source:'experimental_opencv_unvalidated',
    measurement_basis:'grain_count_not_weight',manual_verification_required:true,model_configuration:'hybrid',
    model_validation_scope:'held_out_annotated_masks_only',confidence_note:'not calibrated',
    classes:['broken_grain','chalky_grain','discolored_grain','whole_grain'],total_grains:2,
    counts:{broken_grain:1,chalky_grain:0,discolored_grain:0,whole_grain:1},
    count_percentages:{broken_grain:50,chalky_grain:0,discolored_grain:0,whole_grain:50},
    grains:[{grain_index:0,bbox_xywh:[10,10,5,15],category:'broken_grain',score:0.7},
      {grain_index:1,bbox_xywh:[30,30,5,15],category:'whole_grain',score:0.8}],
    segmentation_warnings:['Unvalidated segmentation'],dss_result:null,official_grade:null});
};
try {
  result=await api('POST',`/evaluations/${id}/screening`,undefined,token,modelEnv);
  assert.equal(result.status,200);assert.equal(result.data.status,'research_preview');
  assert.equal(result.data.result.counts.whole_grain,1);
  result=await api('GET',`/evaluations/${id}/screening`,undefined,token,modelEnv);
  assert.equal(result.data.result.total_grains,2);
  result=await api('POST',`/evaluations/${id}/screening`,undefined,token,modelEnv);
  assert.equal(result.status,409);assert.equal(modelRequests,1);
  result=await api('GET',`/evaluations/${id}/screening`,undefined,other,modelEnv);assert.equal(result.status,404);
  const replace=new FormData();replace.append('image',fakeImage);
  result=await api('POST',`/evaluations/${id}/image`,replace,token,modelEnv);assert.equal(result.status,200);
  result=await api('GET',`/evaluations/${id}/screening`,undefined,token,modelEnv);
  assert.equal(result.data.status,'not_requested');
} finally {globalThis.fetch=modelMock;}
result=await api('DELETE',`/evaluations/${id}`,undefined,token,{IMAGES:images});assert.equal(result.status,204);assert.equal(store.size,0);
result=await api('GET','/evaluations',undefined,token);assert.equal(result.data.length,0);
result=await api('POST','/auth/logout',undefined,token);assert.equal(result.status,204);
result=await api('GET','/auth/me',undefined,token);assert.equal(result.status,401);
result=await api('POST','/auth/forgot-password',{email:'unknown@example.org'});assert.equal(result.status,503);
// Mock the external mail provider (no real emails or network calls).
const oldFetch=globalThis.fetch;
let resetToken;
globalThis.fetch=async (url,opts)=>{
  assert.equal(url,'https://api.resend.com/emails');
  const mail=JSON.parse(opts.body);
  resetToken=mail.text.match(/reset_token=([0-9a-f]{64})/)[1];
  return new Response('{}',{status:200});
};
try {
  const mailEnv={RESEND_API_KEY:'fake-api-key',RESET_FROM_EMAIL:'no-reply@example.org'};
  result=await api('POST','/auth/forgot-password',{email:'student@example.org'},undefined,mailEnv);
  assert.equal(result.status,200);assert.match(resetToken,/^[a-f0-9]{64}$/);
  result=await api('POST','/auth/reset-password',{token:resetToken,new_password:'third-new-long-password-789'});
  assert.equal(result.status,200);
  result=await api('POST','/auth/reset-password',{token:resetToken,new_password:'fourth-new-long-password-999'});
  assert.equal(result.status,400);
  result=await api('POST','/auth/sign-in',{email:'student@example.org',password:'third-new-long-password-789'});
  assert.equal(result.status,200);
} finally { globalThis.fetch=oldFetch; }
console.log('PASS: Cloudflare Pages API + experimental ML bridge tests (auth, D1, R2, ownership, invalidation, password reset)');
