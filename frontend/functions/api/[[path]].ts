/**
 * RiceGrade Cloudflare Pages API — D1 users, sessions, test-mill records, optional R2 images.
 * No PyTorch inference or DSS results are represented as completed here.
 * Same endpoints as the earlier FastAPI prototype so React pages remain compatible.
 */
interface D1Statement {
  bind(...values: unknown[]): D1Statement;
  first<T = Record<string, unknown>>(): Promise<T | null>;
  all<T = Record<string, unknown>>(): Promise<{results: T[]}>;
  run(): Promise<{meta?: {last_row_id?: number}}>;
}
interface D1Database {
  prepare(sql: string): D1Statement;
  batch(statements: D1Statement[]): Promise<unknown>;
}
interface R2Object { body: ReadableStream<Uint8Array> | null; httpMetadata?: {contentType?: string} }
interface R2Bucket {
  put(key: string, value: ArrayBuffer, options?: {httpMetadata: {contentType: string}}): Promise<unknown>;
  get(key: string): Promise<R2Object | null>;
  delete(key: string): Promise<unknown>;
}
interface Env {
  DB?: D1Database;
  IMAGES?: R2Bucket;
  RESEND_API_KEY?: string;
  RESET_FROM_EMAIL?: string;
  RICEGRADE_PUBLIC_URL?: string;
}
interface Context { request: Request; env: Env }
type Row = Record<string, unknown>;
type UserRow = Row & {id: number; email: string; full_name: string; role: string; password_hash: string; password_salt: string; password_iterations: number};
type AssessmentRow = Row & { id: number; user_id: number };
const encoder = new TextEncoder();
const ITERATIONS = 100_000;
const SESSION_DAYS = 7;
const MAX_IMAGE = 5 * 1024 * 1024;
function iso() { return new Date().toISOString(); }
function future(mins: number) { return new Date(Date.now() + mins * 60_000).toISOString(); }
function response(value: unknown, status = 200) {
  return Response.json(value, {status, headers: {'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'}});
}
class ApiError extends Error { constructor(public status: number, message: string) { super(message); } }
function fail(status: number, message: string): never { throw new ApiError(status, message); }
function field(obj: Row, name: string, max = 256): string {
  const val = obj[name];
  if (typeof val !== 'string' || val.length > max) fail(422, `Invalid ${name.replaceAll('_',' ')}`);
  return val;
}
async function body(request: Request): Promise<Row> {
  const text = await request.text();
  if (text.length > 10_000) fail(413, 'Request body is too large');
  try {
    const parsed: unknown = JSON.parse(text);
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) fail(422, 'Invalid request');
    return parsed as Row;
  } catch { fail(422, 'Invalid JSON request'); }
}
function requirePassword(password: string) {
  if (password.length < 12 || password.length > 256) fail(422, 'Password must contain 12–256 characters');
}
function toHex(data: Uint8Array): string { return Array.from(data, b => b.toString(16).padStart(2,'0')).join(''); }
function fromHex(hex: string): Uint8Array {
  if (!/^(?:[a-f0-9]{2})+$/i.test(hex)) fail(500,'Invalid stored password data');
  return Uint8Array.from(hex.match(/../g)!, part => parseInt(part,16));
}
function token(): string {
  const raw = crypto.getRandomValues(new Uint8Array(32));
  return toHex(raw);
}
async function sha256(value: string): Promise<string> {
  return toHex(new Uint8Array(await crypto.subtle.digest('SHA-256', encoder.encode(value))));
}
async function pwHash(password: string, saltHex: string, iterations = ITERATIONS): Promise<string> {
  const key = await crypto.subtle.importKey('raw', encoder.encode(password), 'PBKDF2', false, ['deriveBits']);
  const bits = await crypto.subtle.deriveBits({name:'PBKDF2', salt: fromHex(saltHex) as BufferSource, iterations, hash:'SHA-256'}, key, 256);
  return toHex(new Uint8Array(bits));
}
function matchesHash(a: string, b: string): boolean {
  // Constant-time comparison of identically shaped hexadecimal digests.
  if (a.length !== b.length) return false;
  let diff = 0;
  for (let i=0; i<a.length; i++) diff |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return diff === 0;
}
function publicUser(user: UserRow) { return {id:user.id,email:user.email,full_name:user.full_name,role:user.role}; }
function dbRequired(env: Env): D1Database { if (!env.DB) fail(503,'D1 database binding is missing'); return env.DB; }
function emailAddress(raw: string): string {
  const email = raw.trim().toLowerCase();
  if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) fail(422,'Enter a valid email address');
  return email;
}
function validRole(value: unknown): 'operator'|'qa' {
  if (value !== 'operator' && value !== 'qa') fail(422,'Select Milling Operator or QA/QC Personnel');
  return value;
}
async function createSession(db: D1Database, userId: number): Promise<string> {
  const value = token();
  await db.prepare('INSERT INTO sessions(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)')
    .bind(await sha256(value),userId,iso(),future(7*24*60)).run();
  return value;
}
async function activeSession(request: Request, db: D1Database): Promise<{user:UserRow; rawToken:string}> {
  const auth = request.headers.get('Authorization') ?? '';
  if (!/^Bearer [a-f0-9]{64}$/i.test(auth)) fail(401,'Authentication required');
  const rawToken = auth.slice(7);
  const row = await db.prepare(`SELECT u.* FROM sessions s JOIN users u ON u.id=s.user_id
    WHERE s.token_hash=? AND s.expires_at>?`).bind(await sha256(rawToken),iso()).first<UserRow>();
  if (!row) fail(401,'Your session has expired. Please sign in again.');
  return {user:row,rawToken};
}
async function checkLimit(db: D1Database, email: string): Promise<string> {
  const key = await sha256(email);
  const attempt = await db.prepare('SELECT attempts,window_start FROM login_attempts WHERE email_key=?').bind(key).first<{attempts:number;window_start:string}>();
  if (attempt && Date.now()-Date.parse(attempt.window_start)<15*60_000 && attempt.attempts >= 8) fail(429,'Too many attempts. Try again in 15 minutes.');
  return key;
}
async function badAttempt(db: D1Database, key: string) {
  const now = iso();
  await db.prepare(`INSERT INTO login_attempts(email_key,attempts,window_start) VALUES(?,1,?)
    ON CONFLICT(email_key) DO UPDATE SET
    attempts=CASE WHEN window_start<? THEN 1 ELSE attempts+1 END,
    window_start=CASE WHEN window_start<? THEN excluded.window_start ELSE window_start END`)
    .bind(key,now,new Date(Date.now()-15*60_000).toISOString(),new Date(Date.now()-15*60_000).toISOString()).run();
}
function parseNumber(obj: Row, fieldName: string, required: boolean): number|null {
  const value = obj[fieldName];
  if ((value === null || value === undefined || value === '') && !required) return null;
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0) fail(422,`Enter a positive numeric ${fieldName.replaceAll('_',' ')}`);
  return value;
}
function validateEval(p:Row) {
  const lot = field(p,'lot_id',80).trim(); const run = field(p,'test_run_id',80).trim();
  const date = field(p,'test_date',10);
  if (!lot || !run || !/^\d{4}-\d{2}-\d{2}$/.test(date) || Number.isNaN(Date.parse(`${date}T00:00:00Z`))) fail(422,'Valid lot, test-run, and date are required');
  const paddy = parseNumber(p,'paddy_input_weight',true)!;
  const milled = parseNumber(p,'total_milled_rice_weight',true)!;
  const brown = parseNumber(p,'brown_rice_weight',false);
  const head = parseNumber(p,'head_rice_weight',false);
  const moisture = parseNumber(p,'moisture_content',false);
  const notes = field(p,'machine_notes',2000);
  if (milled > paddy) fail(422,'Total milled rice cannot exceed paddy input');
  if (brown !== null && (brown < milled || brown > paddy)) fail(422,'Brown rice weight must be between milled rice and paddy input');
  if (head !== null && head > milled) fail(422,'Head rice weight cannot exceed total milled rice');
  if (moisture !== null && moisture > 100) fail(422,'Moisture content must be at most 100%');
  return {lot,run,date,paddy,milled,brown,head,moisture,notes};
}
async function owned(db:D1Database,id:number, userId:number):Promise<AssessmentRow> {
  if (!Number.isSafeInteger(id) || id<=0) fail(404,'Assessment not found');
  const row=await db.prepare('SELECT * FROM assessments WHERE id=? AND user_id=?').bind(id,userId).first<AssessmentRow>();
  if(!row)fail(404,'Assessment not found');
  return row;
}
async function serializeEval(db:D1Database,row:AssessmentRow):Promise<Row> {
  const image=await db.prepare('SELECT 1 FROM assessment_images WHERE assessment_id=?').bind(row.id).first();
  return {...row,has_image:!!image};
}
async function sendReset(env:Env, to:string, rawToken:string): Promise<void> {
  const apiKey=env.RESEND_API_KEY;
  const from=env.RESET_FROM_EMAIL;
  if (!apiKey || !from) fail(503,'Password-reset email is not configured. Contact your administrator.');
  const base=(env.RICEGRADE_PUBLIC_URL || 'https://ricegrade.pages.dev').replace(/\/$/,'');
  const url=`${base}/?reset_token=${encodeURIComponent(rawToken)}`;
  const res=await fetch('https://api.resend.com/emails',{
    method:'POST',headers:{Authorization:`Bearer ${apiKey}`,'Content-Type':'application/json'},
    body:JSON.stringify({from,to,subject:'RiceGrade password reset',text:`A password reset was requested for your RiceGrade account.\n\nOpen within 30 minutes:\n${url}\n\nIf this was not you, ignore this message.`})
  });
  if (!res.ok) fail(503,'Password reset email service is unavailable. Please retry later.');
}
function imageType(data:Uint8Array):string|null {
  if(data.length>12 && data[0]===0xff && data[1]===0xd8 && data[2]===0xff) return 'image/jpeg';
  if(data.length>12 && toHex(data.subarray(0,8))==='89504e470d0a1a0a') return 'image/png';
  if(data.length>12 && toHex(data.subarray(0,4))==='52494646' && toHex(data.subarray(8,12))==='57454250') return 'image/webp';
  return null;
}
async function router(request:Request,env:Env):Promise<Response> {
  const db=dbRequired(env);
  const url=new URL(request.url);
  const path=url.pathname.replace(/\/+$/,'') || '/';
  const method=request.method.toUpperCase();
  if (path==='/api/health' && method==='GET') {
    const exists=await db.prepare("SELECT name FROM sqlite_master WHERE type='table' AND name='users'").first();
    return response({status:exists?'ok':'schema_missing',service:'ricegrade-cloudflare-api',database:exists?'ready':'uninitialized'},exists?200:503);
  }
  if (path==='/api/auth/sign-up' && method==='POST') {
    const p=await body(request);
    const email=emailAddress(field(p,'email'));const name=field(p,'full_name',120).trim();const role=validRole(p.role);
    if(name.length<2)fail(422,'Full name must be at least 2 characters');
    const password=field(p,'password');requirePassword(password);
    if(await db.prepare('SELECT id FROM users WHERE email=?').bind(email).first()) fail(409,'An account with this email already exists');
    const salt=toHex(crypto.getRandomValues(new Uint8Array(16)));
    const hash=await pwHash(password,salt);
    try {
      const result=await db.prepare(`INSERT INTO users(email,full_name,role,password_hash,password_salt,password_iterations,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?)`).bind(email,name,role,hash,salt,ITERATIONS,iso(),iso()).run();
      const id=result.meta?.last_row_id;
      if (!id) fail(500,'Account could not be created');
      const access=await createSession(db,id);
      return response({access_token:access,token_type:'bearer',user:{id,email,full_name:name,role}},201);
    }catch (e){if(String(e).includes('UNIQUE'))fail(409,'An account with this email already exists'); throw e;}
  }
  if (path==='/api/auth/sign-in' && method==='POST') {
    const p=await body(request);const email=emailAddress(field(p,'email'));const password=field(p,'password');
    const key=await checkLimit(db,email);
    const user=await db.prepare('SELECT * FROM users WHERE email=?').bind(email).first<UserRow>();
    const salt=user?.password_salt || '00000000000000000000000000000000';
    const expected=user?.password_hash || '0'.repeat(64);
    const computed=await pwHash(password,salt,user?.password_iterations || ITERATIONS);
    if(!user || !matchesHash(computed,expected)) {
      await badAttempt(db,key);
      fail(401,'Invalid email or password');
    }
    await db.prepare('DELETE FROM login_attempts WHERE email_key=?').bind(key).run();
    const access=await createSession(db,user.id);
    return response({access_token:access,token_type:'bearer',user:publicUser(user)});
  }
  if (path==='/api/auth/forgot-password' && method==='POST') {
    if(!env.RESEND_API_KEY || !env.RESET_FROM_EMAIL)fail(503,'Password reset email is not configured. Contact your administrator.');
    const p=await body(request);const email=emailAddress(field(p,'email'));
    // A separate, per-address quota prevents sending repeated reset emails.
    // The check applies to nonexistent addresses too; no account enumeration.
    const resetKey='reset:'+await sha256(email);
    const quota=await db.prepare('SELECT attempts,window_start FROM login_attempts WHERE email_key=?')
      .bind(resetKey).first<{attempts:number;window_start:string}>();
    if (quota && Date.now()-Date.parse(quota.window_start)<60*60_000 && quota.attempts >= 3)
      fail(429,'Too many reset requests. Try again later.');
    const boundary=new Date(Date.now()-60*60_000).toISOString();
    await db.prepare(`INSERT INTO login_attempts(email_key,attempts,window_start) VALUES(?,1,?)
      ON CONFLICT(email_key) DO UPDATE SET
      attempts=CASE WHEN window_start<? THEN 1 ELSE attempts+1 END,
      window_start=CASE WHEN window_start<? THEN excluded.window_start ELSE window_start END`)
      .bind(resetKey,iso(),boundary,boundary).run();
    const user=await db.prepare('SELECT id FROM users WHERE email=?').bind(email).first<{id:number}>();
    if(user){
      const reset=token();const hashed=await sha256(reset);
      await db.prepare('DELETE FROM password_resets WHERE user_id=?').bind(user.id).run();
      await db.prepare('INSERT INTO password_resets(token_hash,user_id,created_at,expires_at) VALUES(?,?,?,?)')
        .bind(hashed,user.id,iso(),future(30)).run();
      try {await sendReset(env,email,reset);} catch(e) {await db.prepare('DELETE FROM password_resets WHERE token_hash=?').bind(hashed).run();throw e;}
    }
    return response({message:'If an account exists, a password-reset link will be sent to that address.'});
  }
  if (path==='/api/auth/reset-password' && method==='POST') {
    const p=await body(request);const reset=field(p,'token');const password=field(p,'new_password');requirePassword(password);
    if(!/^[a-f0-9]{64}$/i.test(reset))fail(400,'This reset link is invalid or expired');
    const key=await sha256(reset);
    const rec=await db.prepare('SELECT * FROM password_resets WHERE token_hash=? AND used_at IS NULL AND expires_at>?').bind(key,iso())
      .first<{user_id:number}>();
    if(!rec)fail(400,'This reset link is invalid or expired');
    const salt=toHex(crypto.getRandomValues(new Uint8Array(16)));
    const hashed=await pwHash(password,salt);
    // Conditional UPDATE prevents reuse of this token if two requests race.
    const claim=await db.prepare('UPDATE password_resets SET used_at=? WHERE token_hash=? AND used_at IS NULL AND expires_at>?').bind(iso(),key,iso()).run();
    if (claim.meta && 'changes' in claim.meta && Number((claim.meta as Row).changes)===0)fail(400,'This reset link is invalid or expired');
    await db.batch([
      db.prepare('UPDATE users SET password_salt=?,password_hash=?,password_iterations=?,updated_at=? WHERE id=?')
        .bind(salt,hashed,ITERATIONS,iso(),rec.user_id),
      db.prepare('DELETE FROM sessions WHERE user_id=?').bind(rec.user_id),
    ]);
    return response({message:'Password reset successful. Sign in with your new password.'});
  }
  // All routes below require the user's own unexpired bearer session.
  if(path.startsWith('/api/auth/') || path.startsWith('/api/evaluations')) {
    const {user,rawToken}=await activeSession(request,db);
    if(path==='/api/auth/me' && method==='GET')return response(publicUser(user));
    if(path==='/api/auth/logout' && method==='POST'){
      await db.prepare('DELETE FROM sessions WHERE token_hash=?').bind(await sha256(rawToken)).run();
      return new Response(null,{status:204,headers:{'Cache-Control':'no-store'}});
    }
    if(path==='/api/auth/profile' && method==='PATCH'){
      const p=await body(request);const name=field(p,'full_name',120).trim();const role=validRole(p.role);
      if(name.length<2)fail(422,'Full name must be at least 2 characters');
      await db.prepare('UPDATE users SET full_name=?,role=?,updated_at=? WHERE id=?').bind(name,role,iso(),user.id).run();
      return response({...publicUser(user),full_name:name,role});
    }
    if(path==='/api/auth/change-password' && method==='POST'){
      const p=await body(request);const previous=field(p,'current_password');const updated=field(p,'new_password');requirePassword(updated);
      if(previous===updated)fail(422,'Choose a different new password');
      const check=await pwHash(previous,user.password_salt,user.password_iterations);
      if(!matchesHash(check,user.password_hash))fail(400,'Current password is incorrect');
      const salt=toHex(crypto.getRandomValues(new Uint8Array(16)));
      const hash=await pwHash(updated,salt);
      await db.batch([
        db.prepare('UPDATE users SET password_salt=?,password_hash=?,password_iterations=?,updated_at=? WHERE id=?')
          .bind(salt,hash,ITERATIONS,iso(),user.id),
        db.prepare('DELETE FROM sessions WHERE user_id=? AND token_hash!=?').bind(user.id,await sha256(rawToken)),
      ]);
      return response({message:'Password updated. Other sessions have been signed out.'});
    }
    if(path==='/api/evaluations' && method==='GET'){
      const {results}=await db.prepare(`SELECT a.*, CASE WHEN ai.assessment_id IS NULL THEN 0 ELSE 1 END AS has_image
        FROM assessments a LEFT JOIN assessment_images ai ON ai.assessment_id=a.id WHERE a.user_id=? ORDER BY a.created_at DESC,a.id DESC`)
        .bind(user.id).all<Row>();
      return response(results.map(row=>({...row,has_image:!!row.has_image})));
    }
    if(path==='/api/evaluations' && method==='POST'){
      const p=validateEval(await body(request));
      const now=iso();
      try{
        const result=await db.prepare(`INSERT INTO assessments(user_id,lot_id,test_run_id,test_date,paddy_input_weight,total_milled_rice_weight,
          brown_rice_weight,head_rice_weight,moisture_content,machine_notes,total_milling_recovery,brown_rice_recovery,
          head_rice_recovery,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)`)
          .bind(user.id,p.lot,p.run,p.date,p.paddy,p.milled,p.brown,p.head,p.moisture,p.notes,100*p.milled/p.paddy,
            p.brown===null?null:100*p.brown/p.paddy,p.head===null?null:100*p.head/p.paddy,'awaiting_model',now,now).run();
        const id=result.meta?.last_row_id;
        if(!id)fail(500,'Assessment could not be saved');
        return response({...p,id,user_id:user.id,lot_id:p.lot,test_run_id:p.run,test_date:p.date,paddy_input_weight:p.paddy,
          total_milled_rice_weight:p.milled,brown_rice_weight:p.brown,head_rice_weight:p.head,moisture_content:p.moisture,
          machine_notes:p.notes,total_milling_recovery:100*p.milled/p.paddy,
          brown_rice_recovery:p.brown===null?null:100*p.brown/p.paddy,
          head_rice_recovery:p.head===null?null:100*p.head/p.paddy,
          status:'awaiting_model',created_at:now,updated_at:now,has_image:false},201);
      }catch(e){if(String(e).includes('UNIQUE'))fail(409,'This test-run ID already exists in your account');throw e;}
    }
    const match=path.match(/^\/api\/evaluations\/(\d+)(?:\/(image))?$/);
    if(match){
      const id=Number(match[1]);
      const assessment=await owned(db,id,user.id);
      if(!match[2]){
        if(method==='GET')return response(await serializeEval(db,assessment));
        if(method==='DELETE'){
          const meta=await db.prepare('SELECT object_key FROM assessment_images WHERE assessment_id=?').bind(id).first<{object_key:string}>();
          if(meta && env.IMAGES)await env.IMAGES.delete(meta.object_key);
          await db.prepare('DELETE FROM assessments WHERE id=? AND user_id=?').bind(id,user.id).run();
          return new Response(null,{status:204,headers:{'Cache-Control':'no-store'}});
        }
      }
      if(match[2]==='image'){
        const bucket=env.IMAGES;
        if(!bucket)fail(503,'Image storage is not connected yet. Your measurements can still be saved.');
        if(method==='POST'){
          const form=await request.formData();const image=form.get('image');
          if(!(image instanceof File))fail(422,'Select a JPEG, PNG, or WebP image');
          if(image.size===0 || image.size>MAX_IMAGE)fail(413,'Image must be at most 5 MB');
          const data=new Uint8Array(await image.arrayBuffer());
          const media=imageType(data);
          if(!media)fail(422,'Image must be a valid JPEG, PNG, or WebP file');
          const key=`private/assessments/${user.id}/${id}/sample`;
          await bucket.put(key, data.buffer as ArrayBuffer, {httpMetadata:{contentType:media}});
          await db.prepare(`INSERT INTO assessment_images(assessment_id,object_key,media_type,filename,size_bytes,uploaded_at)
            VALUES(?,?,?,?,?,?) ON CONFLICT(assessment_id) DO UPDATE SET object_key=excluded.object_key,
            media_type=excluded.media_type,filename=excluded.filename,size_bytes=excluded.size_bytes,uploaded_at=excluded.uploaded_at`)
            .bind(id,key,media,image.name.slice(0,160),data.byteLength,iso()).run();
          await db.prepare('UPDATE assessments SET updated_at=? WHERE id=?').bind(iso(),id).run();
          return response({has_image:true,size_bytes:data.byteLength,message:'Image saved. ML screening remains pending.'});
        }
        if(method==='GET'){
          const meta=await db.prepare('SELECT object_key,media_type FROM assessment_images WHERE assessment_id=?').bind(id)
            .first<{object_key:string;media_type:string}>();
          if(!meta)fail(404,'No image attached');
          const object=await bucket.get(meta.object_key);
          if(!object || !object.body)fail(404,'Image is not available');
          return new Response(object.body,{headers:{'Content-Type':meta.media_type,'Cache-Control':'private, no-store','X-Content-Type-Options':'nosniff'}});
        }
      }
    }
  }
  fail(404,'API endpoint not found');
}
export const onRequest = async ({request,env}: Context): Promise<Response> => {
  try { return await router(request,env); }
  catch(error){
    if(error instanceof ApiError)return response({detail:error.message},error.status);
    console.error('RiceGrade API error', error);
    const raw=String(error);
    if(raw.includes('no such table'))return response({detail:'Database tables are not installed. Run the D1 migration before using RiceGrade.'},503);
    return response({detail:'Internal service error. Please try again or contact the administrator.'},500);
  }
};
